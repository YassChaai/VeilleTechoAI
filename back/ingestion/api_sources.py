"""Connecteur API Hacker News (Algolia Search API), format JSON."""

from __future__ import annotations

import os
import time

import requests

from processing.dedup import normalize_title, strip_html

_TIMEOUT = 20
_HEADERS = {"User-Agent": "veille-tech/0.1 (hackathon Epitech)"}


def fetch(source: dict, limit: int) -> list[dict]:
    # `search` (tags=story) trie par pertinence et remonte de vieux posts (2016…).
    # On borne à une fenêtre récente pour ne garder que l'actualité.
    recency_days = int(os.getenv("HN_RECENCY_DAYS", "30"))
    cutoff = int(time.time()) - recency_days * 86400
    resp = requests.get(
        source["url"],
        params={
            "hitsPerPage": limit,
            "numericFilters": f"created_at_i>{cutoff}",
        },
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    hits = resp.json().get("hits", [])

    items: list[dict] = []
    for hit in hits[:limit]:
        title = (hit.get("title") or hit.get("story_title") or "").strip()
        if not title:
            continue
        url = (
            hit.get("url")
            or hit.get("story_url")
            or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        )
        content = strip_html(hit.get("story_text") or "")
        items.append(
            {
                "source": source["name"],
                "url": url,
                "title": title,
                "title_normalized": normalize_title(title),
                "content": content,
                "category": source.get("domain"),
                "published_at": hit.get("created_at") or "",
                "authority": source.get("authority", 0.0),
            }
        )
    return items
