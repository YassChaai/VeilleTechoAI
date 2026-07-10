"""Déduplication et score de pertinence sur une base SQLite en mémoire."""

from datetime import datetime, timezone

import pytest

from processing import dedup, ranking
from storage import db


@pytest.fixture
def conn():
    c = db.get_connection(":memory:")
    db.init_db(c)
    yield c
    c.close()


def _insert(conn, url, title, authority=0.5, published_at=None, content="corps"):
    published_at = published_at or datetime.now(timezone.utc).isoformat()
    return db.insert_article(
        conn,
        {
            "source": url,
            "url": url,
            "title": title,
            "title_normalized": dedup.normalize_title(title),
            "content": content,
            "category": "Tech",
            "published_at": published_at,
            "authority": authority,
        },
    )


def test_run_dedup_marks_near_duplicate(conn):
    _insert(conn, "a", "OpenAI releases GPT-5 model today")
    _insert(conn, "b", "OpenAI releases GPT-5 model today!")  # quasi identique

    marked = dedup.run_dedup(conn)

    assert marked == 1
    assert db.get_article(conn, 2)["duplicate_of_id"] == 1
    # Idempotence : relancer ne re-marque rien.
    assert dedup.run_dedup(conn) == 0


def test_distinct_titles_are_not_deduplicated(conn):
    _insert(conn, "a", "Apple dévoile un nouveau processeur")
    _insert(conn, "b", "Google lance un service de cloud")
    assert dedup.run_dedup(conn) == 0


def test_relevance_increases_with_authority(conn):
    now = datetime.now(timezone.utc).isoformat()
    _insert(conn, "hi", "Article autorité haute", authority=0.9, published_at=now)
    _insert(conn, "lo", "Article autorité basse", authority=0.1, published_at=now)

    ranking.compute_relevance(conn)

    assert db.get_article(conn, 1)["relevance"] > db.get_article(conn, 2)["relevance"]


def test_relevance_increases_with_freshness(conn):
    fresh = datetime.now(timezone.utc).isoformat()
    old = "2000-01-01T00:00:00+00:00"
    _insert(conn, "new", "Récent", authority=0.5, published_at=fresh)
    _insert(conn, "old", "Ancien", authority=0.5, published_at=old)

    ranking.compute_relevance(conn)

    assert db.get_article(conn, 1)["relevance"] > db.get_article(conn, 2)["relevance"]
