"""Bonus : score de pertinence enrichi.

Combine, dans [0..1] :
  - l'autorité éditoriale de la source ;
  - la fraîcheur (décroissance linéaire sur ~14 jours) ;
  - le nombre de sources croisées (corroboration via `duplicate_of_id`).
"""

from __future__ import annotations

from datetime import datetime, timezone

from processing.dedup import _parse_dt
from storage import db

# Pondérations (somme = 1.0).
W_AUTHORITY = 0.55
W_RECENCY = 0.30
W_CROSS = 0.15

RECENCY_DAYS = 14.0        # au-delà, fraîcheur = 0
CROSS_SCALE = 3.0          # nb de sources croisées pour un score max


def compute_relevance(conn) -> int:
    """(Re)calcule le score de pertinence de chaque article canonique."""
    rows = db.canonical_for_ranking(conn)
    counts = db.duplicate_counts(conn)  # 1 requête au lieu d'un COUNT par article
    now = datetime.now(timezone.utc)
    updated = 0

    for row in rows:
        authority = float(row["authority"] or 0.0)

        age_days = max((now - _parse_dt(row)).total_seconds() / 86400.0, 0.0)
        recency = max(0.0, 1.0 - age_days / RECENCY_DAYS)

        crossed = counts.get(row["id"], 0)
        cross = min(crossed / CROSS_SCALE, 1.0)

        score = W_AUTHORITY * authority + W_RECENCY * recency + W_CROSS * cross
        db.update_relevance(conn, row["id"], round(score, 4))
        updated += 1

    return updated
