"""Découverte de sources (helpers purs, sans réseau) + auto-élagage."""

import time

import pytest

import main
from ingestion import discovery
from processing import source_health
from storage import db


# --- Autodécouverte de flux (parsing pur) ----------------------------------

def test_feeds_from_html_extracts_rss_and_atom():
    html = (
        '<head>'
        '<link rel="alternate" type="application/rss+xml" href="/feed.xml" title="RSS">'
        '<link rel="alternate" type="application/atom+xml" href="https://x.com/atom">'
        '<link rel="stylesheet" href="/style.css">'
        '</head>'
    )
    feeds = discovery._feeds_from_html(html, "https://x.com")
    assert "https://x.com/feed.xml" in feeds       # relatif résolu
    assert "https://x.com/atom" in feeds           # absolu conservé
    assert all("style.css" not in f for f in feeds)  # non-feed ignoré


def test_root_and_host():
    assert discovery._root("https://sub.example.com/path?x=1") == "https://sub.example.com"
    assert discovery._root("example.com") == "https://example.com"
    assert discovery._host("https://example.com/feed") == "example.com"


# --- Scoring on-topic -------------------------------------------------------

def test_ontopic_score_uses_domain_keywords():
    blobs = ["New GPU and processor benchmark", "A recipe for bread", "Kernel security patch"]
    score = discovery._ontopic_score(blobs, "Tech")
    assert 0 < score < 1  # 2 entrées sur 3 sont on-topic


def test_ontopic_score_zero_when_offtopic():
    assert discovery._ontopic_score(["cooking pasta at home"], "Tech") == 0.0


def test_entry_dt_parses_and_defaults_none():
    entry = {"published_parsed": time.struct_time((2026, 7, 1, 12, 0, 0, 0, 0, 0))}
    dt = discovery._entry_dt(entry)
    assert dt is not None and dt.year == 2026
    assert discovery._entry_dt({}) is None


# --- Auto-élagage (DB en mémoire, sans réseau) -----------------------------

@pytest.fixture
def conn():
    c = db.get_connection(":memory:")
    db.init_db(c)
    yield c
    c.close()


def _add(conn, url, origin, quality, runs, active=1):
    db.upsert_source(conn, {
        "name": url, "type": "rss", "url": url, "domain": "Tech",
        "authority": 0.5, "origin": origin,
    })
    sid = conn.execute("SELECT id FROM sources WHERE url = ?", (url,)).fetchone()["id"]
    conn.execute(
        "UPDATE sources SET quality = ?, runs = ?, active = ? WHERE id = ?",
        (quality, runs, active, sid),
    )
    conn.commit()
    return sid


def _active(conn, sid):
    return conn.execute("SELECT active FROM sources WHERE id = ?", (sid,)).fetchone()["active"]


def test_prune_disables_weak_discovered(conn, monkeypatch):
    monkeypatch.setenv("SOURCE_QUALITY_MIN", "0.5")
    monkeypatch.setenv("SOURCE_MIN_RUNS", "2")
    sid = _add(conn, "http://weak", "discovered", quality=0.1, runs=3)
    assert source_health.prune(conn) == 1
    assert _active(conn, sid) == 0


def test_prune_never_touches_static(conn, monkeypatch):
    monkeypatch.setenv("SOURCE_QUALITY_MIN", "0.5")
    monkeypatch.setenv("SOURCE_MIN_RUNS", "1")
    sid = _add(conn, "http://socle", "static", quality=0.0, runs=9)
    assert source_health.prune(conn) == 0
    assert _active(conn, sid) == 1


def test_prune_keeps_recent_discovered_below_min_runs(conn, monkeypatch):
    monkeypatch.setenv("SOURCE_QUALITY_MIN", "0.5")
    monkeypatch.setenv("SOURCE_MIN_RUNS", "3")
    sid = _add(conn, "http://new", "discovered", quality=0.1, runs=1)
    assert source_health.prune(conn) == 0  # runs < min_runs → laissée le temps de faire ses preuves
    assert _active(conn, sid) == 1


# --- Union socle + découvertes actives -------------------------------------

def test_load_sources_union_includes_active_discovered(conn):
    _add(conn, "http://discovered-feed", "discovered", quality=0.4, runs=1, active=1)
    urls = {s["url"] for s in main.load_sources(conn)}
    assert "http://discovered-feed" in urls                 # découverte active
    assert "https://techcrunch.com/feed/" in urls           # socle YAML


def test_load_sources_excludes_pruned_discovered(conn):
    _add(conn, "http://pruned-feed", "discovered", quality=0.0, runs=5, active=0)
    urls = {s["url"] for s in main.load_sources(conn)}
    assert "http://pruned-feed" not in urls                 # élaguée → non ingérée
