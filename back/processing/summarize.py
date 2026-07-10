"""Résumé + catégorisation.

Deux modes :
  - dégradé (défaut, sans clé) : catégorie par mots-clés + résumé. Si un LLM local
    génératif (Ollama) est présent, le résumé est une *vulgarisation FR* rédigée à
    partir de l'article complet ; sinon repli extractif (+ traduction Argos éventuelle) ;
  - IA (si ANTHROPIC_API_KEY présente) : un appel Claude par article renvoyant
    {summary, category, takeaways} en JSON structuré, avec fallback silencieux vers le dégradé.
"""

from __future__ import annotations

import json
import os
import re

from processing import translate
from processing.dedup import strip_html

# Les 4 domaines exacts imposés par le sujet.
DOMAINS = [
    "Tech",
    "Business de la tech",
    "Data & IA",
    "UX & solutions numériques",
]

# Dictionnaire mots-clés -> domaine (mode dégradé).
KEYWORDS: dict[str, list[str]] = {
    "Data & IA": [
        "ai", "a.i", "artificial intelligence", "intelligence artificielle",
        "machine learning", "deep learning", "llm", "gpt", "model", "modèle",
        "neural", "dataset", "data", "données", "transformer", "inference",
        "training", "openai", "anthropic", "mistral",
    ],
    "UX & solutions numériques": [
        "ux", "ui", "design", "usability", "utilisabilité", "accessibility",
        "accessibilité", "user experience", "expérience utilisateur", "interface",
        "figma", "prototype", "wireframe", "typography", "typographie", "css",
    ],
    "Business de la tech": [
        "startup", "funding", "levée de fonds", "ipo", "acquisition", "merger",
        "venture", "valuation", "revenue", "chiffre d'affaires", "layoffs",
        "licenciements", "ceo", "market", "marché", "investors", "investisseurs",
        "raise", "series a", "series b",
    ],
    "Tech": [
        "chip", "processor", "processeur", "gpu", "smartphone", "iphone",
        "android", "browser", "navigateur", "linux", "windows", "security",
        "sécurité", "vulnerability", "vulnérabilité", "open source", "hardware",
        "software", "cloud", "api", "kernel",
    ],
}

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


# --- Mode dégradé -----------------------------------------------------------

def _extractive_summary(title: str, content: str, max_sentences: int = 3,
                        max_chars: int = 400) -> str:
    text = strip_html(content).strip()
    if not text:
        return title.strip()
    sentences = [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]
    summary = " ".join(sentences[:max_sentences])
    if len(summary) > max_chars:
        summary = summary[:max_chars].rsplit(" ", 1)[0] + "…"
    return summary or title.strip()


def _keyword_category(title: str, content: str, default: str | None) -> str:
    haystack = f"{title} {strip_html(content)}".lower()
    scores = {
        domain: sum(haystack.count(kw) for kw in kws)
        for domain, kws in KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    if default in DOMAINS:
        return default
    return DOMAINS[0]


def _extractive_takeaways(title: str, content: str, max_points: int = 4) -> list[str]:
    """Points à retenir (mode dégradé) = phrases informatives extraites du contenu."""
    text = strip_html(content).strip()
    sentences = [s.strip() for s in _SENTENCE_RE.split(text) if len(s.strip()) >= 40]
    points = sentences[:max_points]
    return points or [title.strip()]


def _degraded(title: str, content: str, default: str | None) -> dict:
    # 1. Si un LLM local génératif est dispo (Ollama) : vraie vulgarisation FR
    #    rédigée à partir de l'article complet (pas une simple traduction), avec
    #    la catégorie produite dans le même appel.
    vulg = translate.vulgarize_fr(title, content, DOMAINS)
    if vulg is not None:
        category = vulg["category"] if vulg["category"] in DOMAINS \
            else _keyword_category(title, content, default)
        return {
            "summary": vulg["summary"],
            "category": category,
            "takeaways": vulg["takeaways"],
        }

    # 2. Vulgarisation FR impossible ce coup-ci (Ollama injoignable, etc.).
    #    REQUIRE_LLM_SUMMARY=1 : on REFUSE d'écrire un résumé anglais qui persisterait
    #    → on renvoie None, l'article reste EN ATTENTE et sera retenté au prochain run
    #    (quand le LLM est de nouveau dispo). Sinon, repli extractif assumé (mode sans LLM).
    if _require_llm():
        return None

    summary = _extractive_summary(title, content)
    takeaways = _extractive_takeaways(title, content)
    if translate.available():
        summary = translate.to_french(summary)
        takeaways = translate.to_french_lines(takeaways)
    return {"summary": summary, "category": _keyword_category(title, content, default),
            "takeaways": takeaways}


# --- Mode IA ----------------------------------------------------------------

# Clé posée par le pipeline : celle du compte qui déclenche le run (BYOK) prime,
# sinon ANTHROPIC_API_KEY (env). Process-global : un seul run à la fois (job gardé).
_KEY_OVERRIDE: str | None = None


def set_api_key(key: str | None) -> None:
    """Force la clé Claude pour ce run (clé du compte déclencheur), ou None → env."""
    global _KEY_OVERRIDE
    _KEY_OVERRIDE = key or None


def current_api_key() -> str | None:
    return _KEY_OVERRIDE or os.getenv("ANTHROPIC_API_KEY")


# Politique « pas de repli anglais » posée par le pipeline (per-run). None → env.
_REQUIRE_OVERRIDE: bool | None = None


def set_require_llm(value: bool | None) -> None:
    global _REQUIRE_OVERRIDE
    _REQUIRE_OVERRIDE = value


def _require_llm() -> bool:
    if _REQUIRE_OVERRIDE is not None:
        return _REQUIRE_OVERRIDE
    return os.getenv("REQUIRE_LLM_SUMMARY") == "1"


def ia_enabled() -> bool:
    """Vrai seulement si une clé est disponible (compte ou env) ET le SDK est installé."""
    if not current_api_key():
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


# Modèles proposés au choix (réglage à chaud via /settings). Le premier est le défaut.
MODEL_CHOICES = [
    {"id": "claude-haiku-4-5-20251001", "label": "Haiku 4.5",
     "hint": "rapide, le moins cher (~0,10 $/run)"},
    {"id": "claude-sonnet-5", "label": "Sonnet 5",
     "hint": "meilleur français (~0,35 $/run)"},
]
_DEFAULT_MODEL = MODEL_CHOICES[0]["id"]

# Override runtime posé par le pipeline (db.get_setting) — sinon on lit ANTHROPIC_MODEL.
_MODEL_OVERRIDE: str | None = None


def set_model(model: str | None) -> None:
    """Force le modèle Claude pour ce process (réglage choisi dans /settings)."""
    global _MODEL_OVERRIDE
    _MODEL_OVERRIDE = model or None


def current_model() -> str:
    """Modèle effectif : override runtime > ANTHROPIC_MODEL > défaut (Haiku)."""
    return _MODEL_OVERRIDE or os.getenv("ANTHROPIC_MODEL") or _DEFAULT_MODEL


def model_label(model_id: str) -> str:
    """Libellé lisible d'un modèle (ex. 'Haiku 4.5'), sinon l'identifiant brut."""
    return next((m["label"] for m in MODEL_CHOICES if m["id"] == model_id), model_id)


_SCHEMA = {
    "type": "object",
    "properties": {
        "title_fr": {"type": "string"},
        "summary": {"type": "string"},
        "takeaways": {"type": "array", "items": {"type": "string"}},
        "category": {"type": "string", "enum": DOMAINS},
    },
    "required": ["title_fr", "summary", "takeaways", "category"],
    "additionalProperties": False,
}


def _ia_enrich(title: str, content: str, default: str | None) -> dict | None:
    """Appel Claude -> {summary, category, takeaways}. None si échec (fallback dégradé)."""
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=current_api_key())
        model = current_model()
        user = f"Titre : {title}\n\nContenu :\n{strip_html(content)[:4000]}"
        resp = client.messages.create(
            model=model,
            max_tokens=700,
            system=(
                "Tu es un assistant de veille technologique. À partir de l'article : "
                "1) traduis le TITRE en français naturel, en gardant TELS QUELS les noms "
                "propres, noms de produits/d'entreprises, acronymes et versions "
                "(ex. Anthropic, GPT-4, IBM Heron, arXiv) ; si le titre est déjà en "
                "français, renvoie-le inchangé ; "
                "2) rédige un résumé de 2 à 3 phrases claires, en français ; "
                "3) donne 3 à 4 points clés à retenir, en français, courts et concrets ; "
                "4) classe l'article dans exactement un des domaines proposés. "
                "Tout le texte produit doit être en français."
            ),
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        )
        text = next(b.text for b in resp.content if b.type == "text")
        data = json.loads(text)
        summary = (data.get("summary") or "").strip()
        if not summary:
            return None
        category = data.get("category")
        if category not in DOMAINS:
            category = default if default in DOMAINS else DOMAINS[0]
        takeaways = [t.strip() for t in (data.get("takeaways") or []) if t.strip()]
        title_fr = (data.get("title_fr") or "").strip()
        return {"title_fr": title_fr or None, "summary": summary,
                "category": category, "takeaways": takeaways}
    except Exception as exc:  # fallback silencieux
        print(f"[ia] échec, bascule en mode dégradé : {exc}")
        return None


# --- Point d'entrée ---------------------------------------------------------

def summarize_and_categorize(article: dict) -> dict | None:
    """Retourne {summary, category, takeaways} pour un article, ou None si REQUIRE_LLM_SUMMARY=1
    et que la vulgarisation FR a échoué (article laissé en attente pour le prochain run)."""
    title = article.get("title", "") or ""
    content = article.get("content", "") or ""
    default = article.get("category")

    if ia_enabled():
        result = _ia_enrich(title, content, default)
        if result is not None:
            return result

    return _degraded(title, content, default)
