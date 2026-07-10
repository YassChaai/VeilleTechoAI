"""Découverte autonome de sources (bonus « système intelligent »).

Un LLM local ne navigue pas : *le code* fait la vraie découverte (recherche web +
autodécouverte de flux RSS), *le LLM local* **propose** des médias réputés par domaine,
et *le code* **valide** chaque flux (existe, se parse, est frais, on-topic). Rien n'est
ajouté sans validation (le petit modèle hallucine des URLs).

Trois couches, toutes optionnelles et dégradé-safe :
  1. autodiscovery depuis un socle de sites curatés (toujours actif) ;
  2. recherche web gratuite via `ddgs` (DISCOVERY_WEB=1) ;
  3. proposition par le LLM local Ollama (DISCOVERY_LLM=1).

Activation générale : SOURCE_DISCOVERY=1. À lancer à la demande (`python main.py discover`),
pas à chaque run (démo reproductible, respect du throttling de ddgs).
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import feedparser
import requests

from processing import summarize, translate
from processing.dedup import strip_html

_HEADERS = {"User-Agent": "veille-tech/0.1 (hackathon Epitech) source-discovery"}
_TIMEOUT = 12

# Socle de sites curatés par domaine (homepages) — autodiscovery toujours possible,
# même sans recherche web ni LLM.
SEED_SITES: dict[str, list[str]] = {
    "Tech": [
        "https://www.theverge.com", "https://arstechnica.com", "https://www.engadget.com",
    ],
    "Business de la tech": [
        "https://techcrunch.com", "https://venturebeat.com", "https://sifted.eu",
    ],
    "Data & IA": [
        "https://huggingface.co/blog", "https://bair.berkeley.edu/blog",
        "https://openai.com/news",
    ],
    "UX & solutions numériques": [
        "https://uxdesign.cc", "https://alistapart.com", "https://www.uxmatters.com",
    ],
}

_COMMON_PATHS = ("/feed", "/feed/", "/rss", "/rss.xml", "/atom.xml", "/index.xml")

_LINK_RE = re.compile(r"<link\b[^>]*>", re.I)
_HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.I)
_TYPE_RE = re.compile(r'type\s*=\s*["\']application/(?:rss|atom)\+xml["\']', re.I)


# --- Config -----------------------------------------------------------------

def enabled() -> bool:
    return os.getenv("SOURCE_DISCOVERY", "0") == "1"


def _fresh_days() -> int:
    return int(os.getenv("DISCOVERY_FRESH_DAYS", "30"))


def _min_recent() -> int:
    return int(os.getenv("DISCOVERY_MIN_RECENT", "3"))


def _max_per_domain() -> int:
    return int(os.getenv("DISCOVERY_MAX_PER_DOMAIN", "3"))


# --- Utilitaires URL --------------------------------------------------------

def _root(url: str) -> str:
    p = urlparse(url if "://" in url else "https://" + url)
    return f"{p.scheme}://{p.netloc}" if p.netloc else url


def _host(url: str) -> str:
    return (urlparse(url).netloc or url).lower().removeprefix("www.")


# --- Couche 1 : autodécouverte de flux --------------------------------------

def _feeds_from_html(html: str, base: str) -> list[str]:
    feeds = []
    for tag in _LINK_RE.findall(html):
        if _TYPE_RE.search(tag):
            m = _HREF_RE.search(tag)
            if m:
                feeds.append(urljoin(base, m.group(1)))
    return feeds


def autodiscover_feeds(site_url: str) -> list[str]:
    """Flux RSS/Atom d'un site : balises <link rel=alternate>, sinon chemins courants."""
    root = _root(site_url)
    try:
        resp = requests.get(root, headers=_HEADERS, timeout=_TIMEOUT)
        link_feeds = _feeds_from_html(resp.text, root) if resp.ok and resp.text else []
    except requests.RequestException:
        link_feeds = []
    if link_feeds:
        return list(dict.fromkeys(link_feeds))
    return [root + path for path in _COMMON_PATHS]


# --- Couche 2 : recherche web (ddgs, optionnel) -----------------------------

def web_enabled() -> bool:
    if os.getenv("DISCOVERY_WEB", "0") != "1":
        return False
    return _import_ddgs() is not None


def _import_ddgs():
    try:
        from ddgs import DDGS
        return DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # ancien nom du paquet
            return DDGS
        except ImportError:
            return None


def _domain_queries(domain: str) -> list[str]:
    return [f"best {domain} blog rss feed", f"meilleurs sites {domain} flux rss"]


def web_search_sites(domain: str, max_results: int = 6) -> set[str]:
    if not web_enabled():
        return set()
    ddgs = _import_ddgs()
    sites: set[str] = set()
    try:
        with ddgs() as search:
            for query in _domain_queries(domain):
                for r in search.text(query, max_results=max_results):
                    url = r.get("href") or r.get("url") or r.get("link")
                    if url:
                        sites.add(_root(url))
                time.sleep(1.0)  # throttle-safe
    except Exception as exc:  # ddgs instable/throttlé : couche ignorée
        print(f"[discover] recherche web indisponible ({exc})")
    return sites


# --- Couche 3 : proposition par le LLM local (optionnel) --------------------

def llm_enabled() -> bool:
    return os.getenv("DISCOVERY_LLM", "0") == "1" and translate.has_generative_llm()


_OUTLET_SCHEMA = {
    "type": "object",
    "properties": {
        "outlets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "site_url": {"type": "string"},
                },
                "required": ["name", "site_url"],
            },
        }
    },
    "required": ["outlets"],
}


def llm_propose_outlets(domain: str, max_outlets: int = 8) -> set[str]:
    """Le LLM propose des médias réputés (nom + URL) ; le code validera ensuite."""
    if not llm_enabled():
        return set()
    prompt = (
        f"Cite jusqu'à {max_outlets} médias, blogs ou publications RÉPUTÉS et ACTIFS "
        f"pour le domaine « {domain} ». Pour chacun, donne le nom et l'URL du site "
        f"(page d'accueil, en https). Réponds STRICTEMENT en JSON :\n"
        '{"outlets":[{"name":"...","site_url":"https://..."}]}'
    )
    try:
        raw = translate._ollama_generate(prompt, num_predict=500, fmt=_OUTLET_SCHEMA)
        data = translate._extract_json(raw)
    except Exception as exc:
        print(f"[discover] proposition LLM indisponible ({exc})")
        return set()
    sites: set[str] = set()
    for outlet in data.get("outlets", []):
        url = (outlet.get("site_url") or "").strip()
        if url.startswith("http"):
            sites.add(_root(url))
    return sites


# --- Validation & scoring ---------------------------------------------------

def _entry_dt(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
    return None


def _ontopic_score(blobs: list[str], domain: str) -> float:
    """Fraction des entrées récentes contenant ≥ 1 mot-clé du domaine."""
    kws = [k.lower() for k in summarize.KEYWORDS.get(domain, [])]
    if not kws or not blobs:
        return 0.0
    hits = sum(1 for b in blobs if any(kw in b.lower() for kw in kws))
    return hits / len(blobs)


def validate_feed(url: str, domain: str) -> dict | None:
    """Vérifie qu'un flux est réel, frais et on-topic ; renvoie un candidat scoré ou None."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
    except Exception:
        return None
    entries = feed.entries or []
    if not entries:
        return None

    now = datetime.now(timezone.utc)
    fresh_days = _fresh_days()
    sample = entries[:20]
    recent = 0
    blobs: list[str] = []
    for e in sample:
        dt = _entry_dt(e)
        if dt and (now - dt).days <= fresh_days:
            recent += 1
        blobs.append(f"{e.get('title', '')} {strip_html(e.get('summary', ''))}")

    if recent < _min_recent():
        return None
    ontopic = _ontopic_score(blobs, domain)
    if ontopic <= 0:
        return None

    freshness_ratio = recent / max(len(sample), 1)
    authority = round(min(0.60, 0.20 + 0.25 * ontopic + 0.15 * freshness_ratio), 3)
    score = round(ontopic * 2 + freshness_ratio + min(recent, 10) / 10, 3)
    title = strip_html((feed.feed.get("title") if feed.feed else "") or _host(url))
    return {
        "name": title[:80] or _host(url),
        "type": "rss",
        "url": url,
        "domain": domain,
        "authority": authority,
        "origin": "discovered",
        "score": score,
        "recent": recent,
        "ontopic": round(ontopic, 3),
    }


# --- Orchestration ----------------------------------------------------------

def discover(existing_urls: set[str], on_progress=None) -> list[dict]:
    """Découvre, valide et score des flux candidats (non encore insérés en base).

    `existing_urls` : URLs déjà connues (socle + découvertes) à ne pas re-proposer.
    `on_progress` : callback optionnel appelé avec {phase, percent, found, validated, kept}
    pour alimenter une barre de progression. Retour : liste de candidats top-N par domaine.
    """
    if not enabled():
        return []
    seen = set(existing_urls)
    # Dédup par nom de domaine : une même publication (venturebeat.com) ne doit pas
    # être ajoutée deux fois via des URLs de flux différentes (/feed vs /feed/…).
    seen_hosts = {_host(u) for u in existing_urls}
    results: list[dict] = []
    domains = summarize.DOMAINS
    n = len(domains)
    found_total = 0
    validated_total = 0

    def emit(phase: str, percent: float) -> None:
        if on_progress:
            on_progress({
                "phase": phase, "percent": int(percent),
                "found": found_total, "validated": validated_total, "kept": len(results),
            })

    emit("Démarrage de la découverte…", 3)
    for i, domain in enumerate(domains):
        emit(f"Recherche · {domain}", 5 + 88 * i / n)
        sites = set(SEED_SITES.get(domain, []))
        sites |= web_search_sites(domain)
        sites |= llm_propose_outlets(domain)
        print(f"[discover] {domain} : {len(sites)} site(s) candidat(s)", flush=True)

        feeds: list[str] = []
        for site in sites:
            for feed_url in autodiscover_feeds(site):
                if feed_url not in seen:
                    feeds.append(feed_url)
        feeds = list(dict.fromkeys(feeds))
        found_total += len(feeds)
        emit(f"Validation des flux · {domain}", 5 + 88 * (i + 0.5) / n)

        scored: list[dict] = []
        for feed_url in feeds:
            if feed_url in seen or _host(feed_url) in seen_hosts:
                continue
            candidate = validate_feed(feed_url, domain)
            if candidate:
                validated_total += 1
                scored.append(candidate)
                seen.add(feed_url)
                seen_hosts.add(_host(feed_url))

        scored.sort(key=lambda d: d["score"], reverse=True)
        keep = scored[: _max_per_domain()]
        for k in keep:
            print(f"[discover]   + {k['name']} — {k['url']} "
                  f"(score {k['score']}, on-topic {k['ontopic']})", flush=True)
        results.extend(keep)
        emit(f"{domain} · {len(keep)} retenue(s)", 5 + 88 * (i + 1) / n)

    emit("Finalisation…", 97)
    return results
