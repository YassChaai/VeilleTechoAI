"""Déduplication à 2 niveaux + utilitaires texte partagés.

Niveau 1 : hash du titre normalisé (identité stricte).
Niveau 2 : difflib.SequenceMatcher ratio > 0.85 sur une fenêtre de 48h.
On ne supprime jamais : on marque `duplicate_of_id` vers l'article canonique.
"""

from __future__ import annotations

import html
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from storage import db

FUZZY_THRESHOLD = 0.85
WINDOW_HOURS = 48

# Petit set de stopwords FR + EN (suffisant pour normaliser des titres).
STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "en", "à", "au",
    "aux", "pour", "par", "sur", "dans", "avec", "sans", "ce", "cet", "cette",
    "the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "with",
    "is", "are", "how", "why", "what", "your", "you",
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]")


def strip_html(text: str) -> str:
    """Retire les balises HTML et normalise les espaces."""
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def normalize_title(title: str) -> str:
    """Titre en minuscules, sans ponctuation ni stopwords."""
    text = strip_html(title).lower()
    text = _NON_ALNUM_RE.sub(" ", text)
    tokens = [w for w in text.split() if w and w not in STOPWORDS]
    return " ".join(tokens)


def _parse_dt(row: sqlite3.Row) -> datetime:
    """Date de l'article (published_at, sinon ingested_at, sinon maintenant)."""
    for key in ("published_at", "ingested_at"):
        raw = row[key] if key in row.keys() else None
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            continue
    return datetime.now(timezone.utc)


def run_dedup(conn: sqlite3.Connection) -> int:
    """Marque les doublons parmi les articles canoniques. Retourne le nombre marqué.

    Idempotent : les articles déjà marqués (`duplicate_of_id` non nul) sont ignorés.
    """
    rows = db.canonical_articles(conn)
    kept: list[tuple[int, str, datetime]] = []  # (id, title_normalized, date)
    marked = 0
    window = timedelta(hours=WINDOW_HOURS)

    for row in rows:
        tnorm = row["title_normalized"]
        dt = _parse_dt(row)
        dup_of = None

        for cid, ctnorm, cdt in kept:
            # Niveau 1 : identité stricte du titre normalisé.
            if tnorm and tnorm == ctnorm:
                dup_of = cid
                break
            # Niveau 2 : similarité floue dans la fenêtre de 48h.
            if abs((dt - cdt).total_seconds()) <= window.total_seconds():
                if SequenceMatcher(None, tnorm, ctnorm).ratio() > FUZZY_THRESHOLD:
                    dup_of = cid
                    break

        if dup_of is not None:
            db.set_duplicate(conn, row["id"], dup_of)
            marked += 1
        else:
            kept.append((row["id"], tnorm, dt))

    return marked
