"""Couche d'ingestion : connecteurs pilotés par sources.yaml.

`fetch_source` applique aussi un **filtre qualité** : une entrée sans corps
exploitable (lien sans texte, ex. certains posts Hacker News, ou « contenu »
qui n'est que le titre) n'a aucune valeur ajoutée — impossible à résumer ou à
vulgariser — donc elle n'entre pas en base. On sur-échantillonne chaque source
puis on ne garde que les `limit` premiers items utiles.
"""

from __future__ import annotations

import os

from ingestion import api_sources, fulltext, rss
from processing.dedup import normalize_title, strip_html


def has_value(item: dict) -> bool:
    """Vrai si l'article a un contenu réellement exploitable (pas un titre seul)."""
    threshold = int(os.getenv("MIN_CONTENT_CHARS", "120"))
    content = strip_html(item.get("content") or "").strip()
    if len(content) < threshold:
        return False
    # « Contenu » qui n'est qu'une reprise du titre → aucune matière à résumer.
    if normalize_title(content) == normalize_title(item.get("title") or ""):
        return False
    return True


def _enrich_thin(items: list[dict], budget: int) -> None:
    """Complète le contenu mince par le texte intégral de la page (bonus qualité).

    Réhabilite les liens sans texte (Hacker News) et les chapôs (TechCrunch) avant
    le filtre qualité. Borné à `budget` téléchargements pour ne pas saturer le réseau.
    """
    threshold = fulltext.min_chars()
    used = 0
    for it in items:
        if used >= budget:
            break
        content = strip_html(it.get("content") or "")
        if len(content) >= threshold:
            continue
        used += 1
        extracted = fulltext.extract(it.get("url", ""))
        if extracted and len(extracted) > len(content):
            it["content"] = extracted


def fetch_source(source: dict, limit: int) -> list[dict]:
    """Récupère les articles d'une source (selon son `type`), filtrés par qualité."""
    kind = source.get("type")
    raw_cap = max(limit * 3, limit)  # sur-échantillonnage pour compenser le filtrage
    if kind == "rss":
        raw = rss.fetch(source, raw_cap)
    elif kind == "api":
        raw = api_sources.fetch(source, raw_cap)
    else:
        raise ValueError(f"Type de source inconnu : {kind!r} ({source.get('name')})")

    if fulltext.enabled():
        _enrich_thin(raw, budget=limit)

    valuable = [it for it in raw if has_value(it)]
    return valuable[:limit]
