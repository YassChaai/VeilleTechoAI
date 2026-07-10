"""Extraction du texte intégral d'une page article (bonus qualité, optionnel).

Beaucoup de flux ne fournissent qu'un extrait (TechCrunch = chapô) voire rien
(Hacker News = lien nu). Pour vulgariser « l'article entier », on va chercher le
corps réel de la page via `trafilatura`.

Activation : `ENRICH_FULLTEXT=1` **et** `trafilatura` installé (`uv add trafilatura`).
Sans l'un ou l'autre, `enabled()` renvoie False et l'ingestion garde le contenu du
flux — aucun impact sur le mode de base. Toute erreur réseau/paywall → `""` (repli
silencieux). Même logique optionnelle que `semantic_search` / `translate`.
"""

from __future__ import annotations

import os

from processing.dedup import strip_html

_available: bool | None = None


def _importable() -> bool:
    try:
        import trafilatura  # noqa: F401
    except ImportError:
        return False
    return True


def enabled() -> bool:
    """Vrai si l'extraction plein texte est demandée ET disponible (mémoïsé)."""
    global _available
    if _available is None:
        _available = os.getenv("ENRICH_FULLTEXT", "0") == "1" and _importable()
    return _available


def min_chars() -> int:
    """Seuil (caractères) sous lequel un contenu est jugé trop mince → extraction."""
    return int(os.getenv("FULLTEXT_MIN_CHARS", "600"))


def extract(url: str) -> str:
    """Texte principal de la page (sans nav/pub), ou "" en cas d'échec."""
    if not url or not enabled():
        return ""
    timeout = int(os.getenv("FULLTEXT_TIMEOUT", "10"))
    try:
        import trafilatura

        downloaded = trafilatura.fetch_url(url, config=_config(timeout))
        if not downloaded:
            return ""
        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
        return strip_html(text or "")
    except Exception as exc:  # repli silencieux : on garde le contenu du flux
        print(f"[fulltext] échec {url} ({exc})")
        return ""


def _config(timeout: int):
    """Config trafilatura avec timeout de téléchargement borné."""
    from trafilatura.settings import use_config

    cfg = use_config()
    cfg.set("DEFAULT", "DOWNLOAD_TIMEOUT", str(timeout))
    return cfg
