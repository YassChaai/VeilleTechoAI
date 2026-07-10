"""Français via un modèle local gratuit (aucune clé API), deux usages :

  - **Vulgarisation** (`vulgarize_fr`) : le LLM local *lit l'article complet* et
    rédige un résumé accessible + des points à retenir, en français, pour quelqu'un
    qui ne connaît pas le sujet. Nécessite un backend génératif (Ollama).
  - **Traduction** (`to_french`) : repli simple quand seul un traducteur est dispo.

Deux backends, essayés dans cet ordre (mode "auto") :
  1. **Ollama** — LLM local (http://localhost:11434), *génératif* : vulgarisation.
     Installer Ollama puis `ollama pull llama3.2:3b`.
  2. **Argos Translate** — traducteur neuronal hors-ligne (`pip install argostranslate`),
     paquet en→fr (~50 Mo) au premier usage. Traduit seulement (pas de vulgarisation).

Si aucun backend n'est disponible, le texte est laissé inchangé (le pipeline
continue de fonctionner). Choix forcé possible via TRANSLATE_BACKEND.
"""

from __future__ import annotations

import json
import os
import re

import requests

from processing.dedup import strip_html

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

_available: bool | None = None
_argos_ready: bool = False


def _ollama_up() -> bool:
    try:
        # Timeout tolérant : sous charge (8 workers), /api/tags peut répondre lentement.
        return requests.get(f"{OLLAMA_HOST}/api/tags", timeout=4).ok
    except requests.RequestException:
        return False


def _argos_importable() -> bool:
    try:
        import argostranslate.translate  # noqa: F401
    except ImportError:
        return False
    return True


def backend() -> str:
    """Backend effectif : 'ollama', 'argos' ou 'none'."""
    forced = os.getenv("TRANSLATE_BACKEND", "auto").lower()
    if forced == "ollama":
        return "ollama" if _ollama_up() else "none"
    if forced == "argos":
        return "argos" if _argos_importable() else "none"
    if forced in ("off", "none"):
        return "none"
    # auto
    if _ollama_up():
        return "ollama"
    if _argos_importable():
        return "argos"
    return "none"


def available() -> bool:
    """Vrai si un backend de traduction est utilisable (mémoïsé pour le run)."""
    global _available
    if _available is None:
        _available = backend() != "none"
    return _available


# --- Backend Ollama ---------------------------------------------------------

def _ollama_generate(prompt: str, system: str | None = None,
                     fmt: str | dict | None = None,
                     num_predict: int | None = None,
                     num_ctx: int | None = None,
                     temperature: float = 0.2,
                     timeout: int = 180) -> str:
    """Appel bas niveau à Ollama /api/generate (réponse non-streamée).

    `fmt` accepte "json" ou un **schéma JSON** (dict) pour forcer une sortie
    structurée valide (Ollama structured outputs). `num_ctx` agrandit la fenêtre
    de contexte (utile pour les longues générations, ex. digest hebdomadaire).
    """
    options: dict = {"temperature": temperature}
    if num_predict is not None:
        options["num_predict"] = num_predict
    if num_ctx is not None:
        options["num_ctx"] = num_ctx
    payload: dict = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": options,
    }
    if system:
        payload["system"] = system
    if fmt is not None:
        payload["format"] = fmt
    resp = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=timeout)
    resp.raise_for_status()
    return (resp.json().get("response") or "").strip()


def _translate_ollama(text: str) -> str:
    prompt = (
        "Traduis le texte suivant en français. "
        "Réponds UNIQUEMENT avec la traduction, sans préambule ni guillemets.\n\n"
        f"{text}"
    )
    return _ollama_generate(prompt)


# --- Vulgarisation (génération, pas traduction) -----------------------------

def has_generative_llm() -> bool:
    """Vrai si un backend capable de *rédiger* (pas seulement traduire) est dispo."""
    return backend() == "ollama"


_VULG_SYSTEM = (
    "Tu es un journaliste spécialisé dans la vulgarisation technologique. "
    "Tu expliques des articles en français simple et clair, à un public curieux "
    "mais non spécialiste. Tu te bases UNIQUEMENT sur le texte fourni ; tu n'inventes rien."
)

_VULG_PROMPT = (
    "Voici un article de veille technologique.\n\n"
    "TITRE : {title}\n\n"
    "CONTENU :\n{content}\n\n"
    "Explique cet article en français à une personne qui ne connaît pas le sujet. "
    "Réponds STRICTEMENT en JSON, sans aucun texte autour, avec les clés "
    "\"resume\", \"points\" et \"categorie\".\n"
    "- \"resume\" : un résumé DÉTAILLÉ et pédagogique de 8 à 12 phrases "
    "(2 à 3 paragraphes) qui, dans l'ordre : (a) pose le contexte et de quoi il "
    "s'agit, (b) explique ce que l'article annonce ou démontre concrètement, "
    "(c) précise pourquoi c'est important et quelles sont les implications. "
    "Langage accessible : évite le jargon, ou explique-le brièvement quand il "
    "est indispensable. Développe les idées plutôt que de les survoler.\n"
    "- \"points\" : 4 à 5 points clés à retenir, courts et concrets.\n"
    "- \"categorie\" : EXACTEMENT une valeur parmi : {categories}.\n"
    "- Tout doit être rédigé en français. N'invente aucune information absente du texte."
)


def _vulg_schema(categories: list[str]) -> dict:
    """Schéma JSON structuré imposé à Ollama (sortie complète et valide garantie)."""
    return {
        "type": "object",
        "properties": {
            "resume": {"type": "string"},
            "points": {"type": "array", "items": {"type": "string"}},
            "categorie": {"type": "string", "enum": list(categories)},
        },
        "required": ["resume", "points", "categorie"],
    }


def _extract_json(raw: str) -> dict:
    """Parse le JSON ; répare a minima en isolant la 1re accolade → dernière."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end > start:
            return json.loads(raw[start : end + 1])
        raise


def vulgarize_fr(title: str, content: str, categories: list[str]) -> dict | None:
    """Résumé vulgarisé + points à retenir + catégorie, EN FRANÇAIS, rédigés par le
    LLM local à partir de l'article complet.

    `categories` : les domaines autorisés (le modèle en choisit exactement un).
    Renvoie {"summary": str, "takeaways": list[str], "category": str|None} ou None
    si aucun backend génératif, contenu trop maigre, ou échec (repli mode dégradé).
    """
    if not has_generative_llm():
        return None
    text = strip_html(content or "").strip()
    if len(text) < 40:  # trop peu de matière pour vulgariser sans inventer
        return None
    prompt = _VULG_PROMPT.format(
        title=(title or "").strip(),
        content=text[:6000],
        categories=", ".join(categories),
    )
    try:
        raw = _ollama_generate(
            prompt, system=_VULG_SYSTEM,
            fmt=_vulg_schema(categories), num_predict=1100,
        )
        data = _extract_json(raw)
    except Exception as exc:  # repli silencieux vers le mode extractif
        print(f"[vulgarize] échec ({exc}) — repli extractif")
        return None
    summary = (data.get("resume") or "").strip()
    points = [str(p).strip() for p in (data.get("points") or []) if str(p).strip()]
    if not summary:
        return None
    category = data.get("categorie")
    if category not in categories:
        category = None  # le mode dégradé retombera sur la catégorie par mots-clés
    return {"summary": summary, "takeaways": points, "category": category}


# --- Backend Argos Translate ------------------------------------------------

def _ensure_argos_pair() -> None:
    """Installe le paquet en→fr d'Argos s'il manque (une seule fois)."""
    global _argos_ready
    if _argos_ready:
        return
    import argostranslate.package
    import argostranslate.translate

    installed = {lang.code for lang in argostranslate.translate.get_installed_languages()}
    if "en" in installed and "fr" in installed:
        _argos_ready = True
        return
    argostranslate.package.update_package_index()
    pkgs = argostranslate.package.get_available_packages()
    pair = next((p for p in pkgs if p.from_code == "en" and p.to_code == "fr"), None)
    if pair:
        argostranslate.package.install_from_path(pair.download())
    _argos_ready = True


def _translate_argos(text: str) -> str:
    import argostranslate.translate

    _ensure_argos_pair()
    return argostranslate.translate.translate(text, "en", "fr")


# --- API publique -----------------------------------------------------------

def to_french(text: str) -> str:
    """Traduit un texte en français ; renvoie l'original si aucun backend/erreur."""
    text = (text or "").strip()
    if not text:
        return text
    b = backend()
    try:
        if b == "ollama":
            return _translate_ollama(text) or text
        if b == "argos":
            return _translate_argos(text) or text
    except Exception as exc:  # repli silencieux : texte inchangé
        print(f"[translate] échec ({exc}) — texte laissé tel quel")
    return text


def to_french_lines(lines: list[str]) -> list[str]:
    """Traduit une liste de lignes (points à retenir) en limitant les appels."""
    lines = [ln.strip() for ln in lines if ln and ln.strip()]
    if not lines or not available():
        return lines
    # Un seul appel : on traduit le bloc joint, puis on resplit.
    joined = "\n".join(lines)
    translated = to_french(joined)
    out = [ln.strip("-• \t") for ln in translated.split("\n") if ln.strip()]
    # Si le découpage ne correspond pas, on retraduit ligne par ligne.
    if len(out) != len(lines):
        return [to_french(ln) for ln in lines]
    return out


# --- Traduction de TITRE (préserve les noms propres, saute le déjà-français) --

_FR_MARKERS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "au", "aux", "et", "ou",
    "en", "dans", "sur", "pour", "par", "avec", "sans", "selon", "votre", "vos",
    "notre", "nos", "son", "sa", "ses", "cette", "ces", "est", "sont", "lance",
    "comment", "pourquoi", "quand", "plus", "ans", "vers", "chez", "entre", "leur",
    "leurs", "qui", "que", "dont", "aussi", "fait", "vient", "devient",
}

_FR_STARTERS = (
    "comment ", "pourquoi ", "voici ", "voilà ", "quand ", "combien ",
    "quel ", "quelle ", "quels ", "où ", "avec ", "dans ",
)

_TITLE_PROMPT = (
    "Traduis en français NATUREL le titre d'article suivant.\n"
    "RÈGLES STRICTES :\n"
    "- Si le titre est DÉJÀ en français, renvoie-le EXACTEMENT tel quel.\n"
    "- Garde INCHANGÉS les noms propres : entreprises, produits, marques, personnes, "
    "et les termes/acronymes techniques (ex. Anthropic, Claude, OpenAI, GPT, iPhone, React).\n"
    "- Ne traduis QUE les mots communs, jamais les noms propres.\n"
    "- Réponds UNIQUEMENT par le titre traduit, sans guillemets ni commentaire.\n\n"
    "Titre : {title}"
)


def _looks_french(text: str) -> bool:
    """Heuristique : le titre est déjà en français (→ ne pas le retraduire)."""
    low = text.lower()
    if any(c in low for c in "àâçéèêëîïôûùüœ"):
        return True
    if low.startswith(_FR_STARTERS):
        return True
    words = set(re.findall(r"[a-z']+", low))
    return len(words & _FR_MARKERS) >= 2


def translate_title(title: str) -> str:
    """Traduit un titre en français en PRÉSERVANT les noms propres. Si le titre est
    déjà en français, il est renvoyé tel quel. Repli sur l'original en cas d'échec."""
    title = (title or "").strip()
    if not title or _looks_french(title):
        return title
    b = backend()
    try:
        if b == "ollama":
            out = _ollama_generate(_TITLE_PROMPT.format(title=title), temperature=0.1)
            return out.strip().strip('"').strip("«»").strip() or title
        if b == "argos":
            return _translate_argos(title) or title
    except Exception as exc:
        print(f"[title] échec ({exc}) — titre laissé tel quel")
    return title
