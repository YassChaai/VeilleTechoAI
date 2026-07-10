"""Boucle d'auto-ajustement de la santé des sources (bonus « intelligent »).

Purement DB (aucun réseau) : à chaque run, on note chaque source d'après la qualité
réelle de ses articles (volume, pertinence moyenne, taux de doublons), on met à jour
une moyenne mobile `quality`, on **élague** les sources découvertes chroniquement
faibles et on **rapproche** leur autorité de la qualité observée.

Le socle (`origin='static'`) est évalué pour l'affichage mais **jamais élagué**.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

from storage import db

_EMA_ALPHA = 0.5  # poids du run courant dans la moyenne mobile


def _host(url: str) -> str:
    return (urlparse(url or "").netloc or (url or "")).lower().removeprefix("www.")


def dedupe_sources(conn) -> int:
    """Supprime les sources DÉCOUVERTES en double (même nom de domaine).

    Conserve, par host, la meilleure : socle d'abord, puis meilleure qualité, puis
    la plus ancienne (id). Ne touche jamais au socle. Retourne le nb supprimé.
    """
    rows = conn.execute("SELECT id, url, origin, quality FROM sources").fetchall()
    ordered = sorted(
        rows,
        key=lambda r: (r["origin"] != "static", -(r["quality"] or 0.0), r["id"]),
    )
    kept_hosts: set[str] = set()
    removed = 0
    for r in ordered:
        host = _host(r["url"])
        if host in kept_hosts:
            if r["origin"] == "discovered":  # on ne supprime jamais le socle
                conn.execute("DELETE FROM sources WHERE id = ?", (r["id"],))
                removed += 1
        else:
            kept_hosts.add(host)
    if removed:
        conn.commit()
    return removed


def _source_signal(conn, name: str) -> float | None:
    """Signal de qualité [0..1] d'une source d'après ses articles, ou None si aucun."""
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN duplicate_of_id IS NOT NULL THEN 1 ELSE 0 END) AS dups,
            SUM(CASE WHEN duplicate_of_id IS NULL THEN 1 ELSE 0 END) AS canon,
            AVG(CASE WHEN duplicate_of_id IS NULL THEN relevance END) AS avg_rel
        FROM articles WHERE source = ?
        """,
        (name,),
    ).fetchone()
    total = row["total"] or 0
    if total == 0:
        return None
    dups = row["dups"] or 0
    canon = row["canon"] or 0
    avg_rel = float(row["avg_rel"] or 0.0)
    volume_norm = min(canon / 5.0, 1.0)
    dup_ratio = dups / total
    # Peu de doublons + articles pertinents + volume suffisant = bonne source.
    return 0.35 * volume_norm + 0.45 * avg_rel + 0.20 * (1.0 - dup_ratio)


def evaluate(conn) -> int:
    """Met à jour la moyenne mobile `quality` de chaque source. Retourne le nb évalué."""
    updated = 0
    for src in db.list_sources(conn):
        signal = _source_signal(conn, src["name"])
        if signal is None:
            continue
        old = float(src["quality"] or 0.0)
        new_q = _EMA_ALPHA * signal + (1.0 - _EMA_ALPHA) * old
        db.update_source_quality(conn, src["id"], new_q)
        updated += 1
    return updated


def prune(conn) -> int:
    """Désactive les sources découvertes chroniquement faibles (jamais le socle)."""
    q_min = float(os.getenv("SOURCE_QUALITY_MIN", "0.15"))
    min_runs = int(os.getenv("SOURCE_MIN_RUNS", "3"))
    pruned = 0
    for src in db.discovered_sources(conn, active_only=True):
        if src["runs"] >= min_runs and float(src["quality"] or 0.0) < q_min:
            db.set_source_active(conn, src["id"], False)
            pruned += 1
    return pruned


def adjust_authority(conn) -> None:
    """Rapproche l'autorité des sources découvertes de leur qualité observée."""
    for src in db.discovered_sources(conn):
        old = float(src["authority"] or 0.5)
        quality = float(src["quality"] or 0.0)
        db.update_source_authority(conn, src["id"], 0.7 * old + 0.3 * quality)


def run(conn) -> tuple[int, int, int]:
    """Dédoublonne → évalue → élague → réajuste.

    Retourne (sources évaluées, sources élaguées, doublons supprimés).
    """
    deduped = dedupe_sources(conn)
    evaluated = evaluate(conn)
    pruned = prune(conn)
    adjust_authority(conn)
    return evaluated, pruned, deduped
