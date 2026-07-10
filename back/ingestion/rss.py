"""Connecteur RSS générique (feedparser), réutilisable pour tout flux."""

from __future__ import annotations

from datetime import datetime, timezone

import feedparser
import requests

from processing.dedup import normalize_title, strip_html

_TIMEOUT = 20
_HEADERS = {"User-Agent": "veille-tech/0.1 (hackathon Epitech)"}


def _published_iso(entry) -> str:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
    return ""


def _richest_content(entry) -> str:
    """Le corps le plus complet dispo : content:encoded > summary > description.

    Beaucoup de flux (Smashing, TechCrunch…) publient l'article entier dans
    `entry.content` ; on le préfère pour permettre une vraie vulgarisation.
    """
    best = ""
    for block in entry.get("content", []) or []:
        value = (block.get("value") or "") if isinstance(block, dict) else ""
        if len(value) > len(best):
            best = value
    fallback = entry.get("summary") or entry.get("description") or ""
    return best if len(best) > len(fallback) else fallback


def fetch(source: dict, limit: int) -> list[dict]:
    # Téléchargement via requests (timeout borné) puis parsing des octets :
    # `feedparser.parse(url)` n'a pas de timeout → un flux qui pend bloque le run.
    resp = requests.get(source["url"], headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    items: list[dict] = []

    for entry in feed.entries[:limit]:
        title = (entry.get("title") or "").strip()
        url = (entry.get("link") or "").strip()
        if not title or not url:
            continue
        content = _richest_content(entry)
        items.append(
            {
                "source": source["name"],
                "url": url,
                "title": title,
                "title_normalized": normalize_title(title),
                "content": strip_html(content),
                "category": source.get("domain"),
                "published_at": _published_iso(entry),
                "authority": source.get("authority", 0.0),
            }
        )
    return items
