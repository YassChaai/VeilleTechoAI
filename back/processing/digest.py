"""Digest éditorial hebdomadaire.

Rédige, pour une semaine donnée, un digest structuré en français (TL;DR + une
section par domaine + signal faible + à suivre) à partir des articles collectés.
Historisé par semaine (table `digests`) → on garde l'historique du dernier mois.

Trois niveaux, dégradé-safe :
  1. Claude (si ANTHROPIC_API_KEY) — meilleure qualité rédactionnelle ;
  2. Ollama (LLM local) — vulgarisation locale gratuite (contexte élargi) ;
  3. dégradé (aucun LLM) — digest assemblé factuellement à partir des résumés
     déjà en base (toujours fonctionnel, sans rien inventer).
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

from processing import summarize, translate
from processing.dedup import strip_html
from storage import db

_MAX_ARTICLES = 40          # cap envoyé au LLM (tient dans le contexte)
_SUMMARY_CHARS = 220        # troncature du résumé de chaque article dans le prompt

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


# --- Bornes de semaine ------------------------------------------------------

def week_bounds(ref_date: str | None = None) -> tuple[str, str]:
    """(lundi, dimanche) ISO de la semaine contenant `ref_date` (défaut : aujourd'hui)."""
    if ref_date:
        d = datetime.fromisoformat(ref_date).date()
    else:
        d = datetime.now(timezone.utc).date()
    monday = d - timedelta(days=d.weekday())
    return monday.isoformat(), (monday + timedelta(days=6)).isoformat()


# --- Prompt éditorial -------------------------------------------------------

_SYSTEM = (
    "Tu es rédacteur en chef d'une newsletter de veille technologique. Tu écris en "
    "français, clair et vivant. Tu ne mentionnes QUE des faits présents dans les "
    "articles fournis — tu n'inventes jamais rien."
)

_INSTRUCTIONS = (
    "Tu reçois la liste des articles collectés automatiquement cette semaine "
    "(semaine du {start} au {end}). Produis un digest hebdomadaire structuré, en "
    "français, lisible en 10 à 15 minutes (1800 à 2500 mots).\n\n"
    "CONTRAINTES DE FOND :\n"
    "- Ne mentionne QUE des faits présents dans les articles fournis. N'invente rien.\n"
    "- Si une catégorie n'a aucun article marquant, dis-le en une phrase au lieu de "
    "forcer du contenu.\n"
    "- Priorise la pertinence : sur les articles d'un domaine, ne retiens que les 3 à 5 "
    "vraiment significatifs.\n"
    "- Cite la source de chaque info (nom de la source entre parenthèses).\n\n"
    "STRUCTURE ATTENDUE, dans cet ordre :\n"
    "1. **TL;DR** — 5 à 8 puces max, 1 phrase chacune.\n"
    "2. **Tech** (250-350 mots) — les 3-5 actus tech majeures ; explique pourquoi "
    "chaque info compte.\n"
    "3. **Business de la tech** (250-350 mots) — mouvements stratégiques, levées, "
    "rachats, décisions produit ; accent sur l'impact business.\n"
    "4. **Data & IA** (250-350 mots) — modèles, papers, outils, décisions d'acteurs ; "
    "distingue l'annonce marketing du résultat vérifiable.\n"
    "5. **UX & solutions numériques** (250-350 mots) — tendances d'interface, outils, "
    "retours d'expérience, évolutions d'usage.\n"
    "6. **Signal faible de la semaine** (100-150 mots) — une info mineure ou isolée qui "
    "pourrait annoncer une tendance ; formule-la comme une hypothèse.\n"
    "7. **À suivre** — 3 à 5 puces de sujets à surveiller la semaine prochaine.\n\n"
    "FORMAT : Markdown, titres en `##`. Pour chaque article cité, mets un lien **interne** "
    "au format [texte](/article/ID) en réutilisant EXACTEMENT le lien fourni sous chaque "
    "article ci-dessous — n'invente aucune URL et ne mets jamais de lien externe.\n\n"
    "Voici les articles de la semaine :\n\n{articles}"
)


def _title(a) -> str:
    """Titre FR si disponible, sinon titre original."""
    fr = a["title_fr"] if "title_fr" in a.keys() else None
    return fr or a["title"]


def _format_articles(articles: list) -> str:
    lines = []
    for a in articles:
        summ = strip_html(a["summary"] or "")[:_SUMMARY_CHARS].strip()
        cat = a["category"] or "Non classé"
        day = (a["published_at"] or a["ingested_at"] or "")[:10]
        lines.append(
            f"- [{_title(a)}](/article/{a['id']}) — {a['source']} — {cat} — {day}\n"
            f"  Résumé : {summ}"
        )
    return "\n".join(lines)


def _articles_index(articles: list) -> str:
    """Section finale DÉTERMINISTE : liens internes cliquables vers chaque article,
    groupés par domaine. Garantit des liens même si le LLM les a ignorés dans sa prose."""
    per_domain = 12  # articles_for_week est déjà trié par pertinence → on garde les meilleurs
    lines = ["## Articles de la semaine", ""]
    for cat in summarize.DOMAINS:
        arts = [a for a in articles if (a["category"] or "") == cat][:per_domain]
        if not arts:
            continue
        lines.append(f"### {cat}")
        for a in arts:
            lines.append(f"- [{_title(a)}](/article/{a['id']}) — {a['source']}")
        lines.append("")
    others = [a for a in articles if (a["category"] or "") not in summarize.DOMAINS][:per_domain]
    if others:
        lines.append("### Autres")
        for a in others:
            lines.append(f"- [{_title(a)}](/article/{a['id']}) — {a['source']}")
    return "\n".join(lines).rstrip()


# --- Backends de génération -------------------------------------------------

def _claude_digest(prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic()
    model = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8")
    resp = client.messages.create(
        model=model, max_tokens=4000, system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return next(b.text for b in resp.content if b.type == "text")


def _ollama_digest(prompt: str) -> str:
    # Contexte élargi (8k) et budget de sortie généreux : génération longue.
    return translate._ollama_generate(
        prompt, system=_SYSTEM, num_ctx=8192, num_predict=2600,
        temperature=0.35, timeout=600,
    )


# --- Digest dégradé (aucun LLM) --------------------------------------------

def _first_sentences(text: str, n: int = 2) -> str:
    text = strip_html(text or "").strip()
    if not text:
        return ""
    sents = [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]
    return " ".join(sents[:n])[:320].strip()


def _degraded_digest(articles: list, start: str, end: str) -> str:
    by_cat: dict[str, list] = {d: [] for d in summarize.DOMAINS}
    for a in articles:
        by_cat.setdefault(a["category"] or "Autres", []).append(a)
    top = sorted(articles, key=lambda a: (a["relevance"] or 0), reverse=True)

    out = [f"# Digest — semaine du {start} au {end}", ""]
    out.append("## TL;DR")
    for a in top[:6]:
        out.append(f"- {_title(a)} ({a['source']})")
    out.append("")

    for cat in summarize.DOMAINS:
        arts = by_cat.get(cat, [])[:5]
        out.append(f"## {cat}")
        if not arts:
            out.append("_Rien de marquant cette semaine dans ce domaine._")
        else:
            for a in arts:
                snippet = _first_sentences(a["summary"] or "", 2)
                out.append(f"- **[{_title(a)}](/article/{a['id']})** — {a['source']}. {snippet}")
        out.append("")

    out.append("## Signal faible de la semaine")
    weak = sorted(articles, key=lambda a: (a["relevance"] or 0))
    if weak:
        w = weak[0]
        out.append(
            f"À surveiller : [{_title(w)}](/article/{w['id']}) ({w['source']}) — sujet isolé "
            "qui pourrait annoncer une tendance plus large."
        )
    else:
        out.append("_Aucun signal faible identifié cette semaine._")
    out.append("")

    out.append("## À suivre")
    for a in top[:4]:
        out.append(f"- {_title(a)} ({a['source']})")
    return "\n".join(out)


def _empty_digest(start: str, end: str) -> str:
    return (f"# Digest — semaine du {start} au {end}\n\n"
            "_Aucun article collecté cette semaine._")


# --- Orchestration ----------------------------------------------------------

def generate(conn, week_start: str | None = None):
    """Génère (ou régénère) le digest d'une semaine et l'enregistre. Retourne la ligne."""
    start, end = week_bounds(week_start)
    articles = db.articles_for_week(conn, start, end)

    if not articles:
        db.upsert_digest(conn, start, end, _empty_digest(start, end), 0, "dégradé")
        return db.get_digest(conn, start)

    prompt = _INSTRUCTIONS.format(
        start=start, end=end, articles=_format_articles(articles[:_MAX_ARTICLES])
    )

    content, model = None, None
    if summarize.ia_enabled():
        try:
            content, model = _claude_digest(prompt), "Claude"
        except Exception as exc:
            print(f"[digest] Claude indisponible ({exc})")
    if not content and translate.has_generative_llm():
        try:
            content, model = _ollama_digest(prompt), "Ollama"
        except Exception as exc:
            print(f"[digest] Ollama indisponible ({exc})")
    if not content or len(content.strip()) < 200:
        content, model = _degraded_digest(articles, start, end), "dégradé"

    # Index final déterministe : garantit des liens internes cliquables vers nos articles.
    content = content.strip() + "\n\n" + _articles_index(articles)
    db.upsert_digest(conn, start, end, content, len(articles), model)
    return db.get_digest(conn, start)


def backfill(conn, weeks: int = 4) -> list:
    """Génère les digests des `weeks` dernières semaines qui ont des articles."""
    monday = datetime.fromisoformat(week_bounds()[0]).date()
    results = []
    for i in range(weeks):
        wk = (monday - timedelta(days=7 * i)).isoformat()
        end = (datetime.fromisoformat(wk).date() + timedelta(days=6)).isoformat()
        if not db.articles_for_week(conn, wk, end):
            continue
        results.append(generate(conn, wk))
    return results
