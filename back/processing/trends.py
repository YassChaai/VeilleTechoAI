"""Bonus : détection de tendances et de signaux faibles.

Calculé à la volée (aucune table dédiée). On compare la fréquence des termes sur
une fenêtre récente à une baseline plus ancienne :
  - **tendances** : termes qui montent (fréquence récente élevée et/ou en forte
    hausse par rapport à la baseline) ;
  - **signaux faibles** : termes émergents — rares, absents de la baseline, mais
    déjà relayés par au moins une source.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone

from processing.dedup import STOPWORDS, _parse_dt, strip_html
from processing.summarize import KEYWORDS
from storage import db

# Tokenise en gardant la CASSE (pour détecter acronymes/CamelCase) : un mot commence
# par une lettre puis lettres/chiffres (garde « gpt4 », « h100 », « iPhone », « GPU »).
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")
# Stopwords additionnels : on ne veut PAS de mots-outils/boilerplate (« while »,
# « comments », « would »…) mais des termes représentatifs des domaines (« intelligence »,
# « startup », « sécurité », « modèle », « design »…). Liste large, SANS le vocabulaire
# métier (ai, data, model, design, cloud, api, startup… restent des tendances valides).
_EXTRA_STOP = {
    # anglais : mots-outils / génériques (len >= 4)
    "about", "above", "across", "after", "again", "against", "along", "already",
    "also", "although", "among", "another", "around", "because", "been", "before",
    "being", "below", "besides", "between", "beyond", "both", "cannot", "could",
    "does", "doing", "done", "down", "during", "each", "either", "else", "enough",
    "even", "ever", "every", "everything", "from", "further", "gets", "give", "given",
    "gives", "goes", "going", "gone", "good", "great", "hand", "have", "having",
    "here", "highly", "however", "instead", "into", "itself", "just", "keep", "kind",
    "know", "known", "knows", "last", "later", "least", "less", "like", "likely",
    "long", "look", "looks", "made", "make", "makes", "making", "many", "maybe",
    "mean", "means", "might", "more", "most", "much", "must", "near", "need", "needs",
    "never", "next", "none", "nothing", "often", "once", "only", "onto", "other",
    "others", "over", "part", "past", "perhaps", "please", "quite", "rather", "real",
    "really", "right", "said", "same", "says", "seem", "seems", "seen", "self",
    "several", "shall", "should", "since", "some", "something", "soon", "still",
    "such", "sure", "take", "taken", "takes", "taking", "than", "that", "their",
    "them", "then", "there", "these", "they", "thing", "things", "think", "this",
    "those", "though", "through", "throughout", "thus", "together", "told", "took",
    "toward", "towards", "under", "until", "upon", "used", "uses", "using", "very",
    "want", "wants", "well", "were", "what", "whatever", "when", "where", "whether",
    "which", "while", "whole", "whose", "will", "with", "within", "without", "wont",
    "would", "your", "yours", "yourself", "this", "that", "new",
    # boilerplate web / flux / HN / arXiv
    "arxiv", "abstract", "announce", "announcement", "approach", "article", "articles",
    "based", "blog", "click", "comment", "comments", "cross", "discuss", "email",
    "guide", "home", "http", "https", "image", "images", "intro", "introduction",
    "link", "links", "login", "menu", "method", "methods", "news", "newsletter",
    "online", "page", "pages", "paper", "papers", "post", "posted", "posts", "privacy",
    "propose", "proposed", "read", "reader", "readers", "reply", "replies", "results",
    "review", "share", "show", "shows", "signin", "story", "stories", "subscribe",
    "terms", "type", "replace", "update", "updates", "video", "videos", "watch",
    # temps / génériques non représentatifs
    "day", "days", "hour", "hours", "month", "months", "today", "tomorrow", "tonight",
    "week", "weeks", "year", "years", "people", "someone", "everyone", "world", "stuff",
    "team", "work", "works", "working", "help", "helps", "better", "best", "first",
    "second", "third", "little", "full", "free", "easy",
    # français : mots-outils fréquents
    "vers", "avec", "plus", "tout", "tous", "toute", "toutes", "sans", "leur", "leurs",
    "être", "faire", "cette", "ces", "dans", "pour", "mais", "donc", "comme", "aussi",
    "encore", "entre", "chaque", "quand", "parce", "alors", "depuis", "après", "avant",
    "selon", "elle", "elles", "nous", "vous", "ils", "sont", "était", "sera", "peut",
    "cela", "ceci", "quel", "quelle", "quels",
}


# --- Lexique des domaines (allowlist) --------------------------------------
# Vocabulaire tech/métier. On NE garde comme tendance qu'un terme présent dans ce
# lexique OU qui a une forme technique (voir `_looks_technical`). Tout le reste
# (verbes, adjectifs, mots courants — « expands », « employ », « according »…) est
# écarté par défaut. Le lexique s'étend facilement (ajouter un mot ici).
_EXTRA_LEXICON = {
    # IA / ML
    "ai", "ml", "llm", "llms", "gpt", "model", "models", "neural", "network",
    "networks", "transformer", "transformers", "diffusion", "embedding", "embeddings",
    "inference", "training", "pretraining", "finetuning", "quantization", "multimodal",
    "reasoning", "agent", "agents", "agentic", "rag", "token", "tokens", "prompt",
    "prompting", "alignment", "hallucination", "benchmark", "dataset", "datasets",
    "parameter", "parameters", "weights", "checkpoint", "attention", "encoder",
    "decoder", "generative", "supervised", "unsupervised", "reinforcement", "gradient",
    "convolutional", "recurrent", "nlp", "chatbot", "chatbots", "copilot", "openai",
    "anthropic", "deepmind", "mistral", "gemini", "claude", "llama", "grok", "sora",
    "midjourney", "dalle", "huggingface", "cuda", "tensor", "pytorch", "tensorflow",
    "keras", "jax", "chatgpt", "robotics", "autonomous",
    # Data
    "data", "database", "databases", "sql", "nosql", "postgres", "postgresql", "mysql",
    "sqlite", "mongodb", "redis", "kafka", "spark", "hadoop", "warehouse", "lakehouse",
    "etl", "pipeline", "analytics", "bigquery", "snowflake", "dataframe", "pandas",
    "numpy",
    # Dev / Cloud
    "cloud", "serverless", "kubernetes", "docker", "container", "containers",
    "microservices", "devops", "cicd", "api", "apis", "sdk", "framework", "frameworks",
    "runtime", "compiler", "wasm", "webassembly", "rust", "golang", "python", "java",
    "javascript", "typescript", "react", "nextjs", "vue", "angular", "svelte", "nodejs",
    "deno", "graphql", "rest", "grpc", "webhook", "latency", "throughput", "scalability",
    "observability", "git", "github", "gitlab", "repository", "kernel", "linux", "unix",
    "windows", "macos", "ios", "android", "browser", "chromium", "webkit",
    # Sécurité
    "security", "cybersecurity", "vulnerability", "vulnerabilities", "exploit",
    "exploits", "malware", "ransomware", "phishing", "breach", "breaches", "encryption",
    "cryptography", "authentication", "oauth", "zeroday", "patch", "backdoor",
    "firewall", "ddos", "cve", "botnet", "spyware",
    # Hardware / semi
    "chip", "chips", "chipset", "semiconductor", "semiconductors", "processor",
    "processors", "cpu", "gpu", "gpus", "tpu", "npu", "silicon", "wafer", "arm",
    "risc", "transistor", "foundry", "tsmc", "nvidia", "amd", "intel", "qualcomm",
    # Business / startup
    "startup", "startups", "funding", "seed", "series", "valuation", "ipo",
    "acquisition", "merger", "acquires", "venture", "revenue", "arr", "mrr", "churn",
    "unicorn", "layoffs", "ceo", "cto", "cfo", "fintech", "edtech", "biotech", "saas",
    "paas", "iaas", "b2b", "b2c", "monetization", "subscription", "ecommerce",
    "marketplace", "investors", "investment", "antitrust", "regulation", "regulatory",
    # UX / design
    "ux", "ui", "design", "designer", "usability", "accessibility", "wireframe",
    "prototype", "prototyping", "typography", "figma", "sketch", "interface",
    "interfaces", "interaction", "onboarding", "responsive", "dashboard", "component",
    "components", "css", "tailwind", "animation", "personas", "wcag",
    # Émergents / autres
    "blockchain", "crypto", "cryptocurrency", "bitcoin", "ethereum", "web3", "nft",
    "defi", "metaverse", "quantum", "vr", "xr", "spatial", "wearable", "iot", "drone",
    "satellite", "genomics", "crispr", "fusion", "battery",
    # Grands acteurs
    "apple", "google", "microsoft", "meta", "amazon", "tesla", "spacex", "netflix",
    "uber", "stripe", "shopify", "oracle", "salesforce", "adobe", "ibm", "samsung",
    "huawei", "tiktok", "bytedance", "reddit", "discord", "slack", "notion", "canva",
    "spotify",
}

# Vocabulaire final = mots des catégories (summarize.KEYWORDS, découpés) + lexique.
TECH_TERMS = {
    w.lower()
    for phrase in (kw for kws in KEYWORDS.values() for kw in kws)
    for w in phrase.split()
    if len(w) >= 2
} | _EXTRA_LEXICON


def _looks_technical(tok: str) -> bool:
    """Forme « jargon » : versionné (gpt4, h100), acronyme (GPU, LLM, RAG),
    ou CamelCase (OpenAI, PyTorch, iPhone) — capte les termes hors lexique."""
    if any(c.isdigit() for c in tok):
        return True
    if tok.isupper() and 2 <= len(tok) <= 6:
        return True
    return bool(re.search(r"[a-z][A-Z]", tok))


def _terms(text: str) -> set[str]:
    """Termes 'domaine/jargon' d'un texte : dans le lexique, ou de forme technique.
    Les verbes/adjectifs/mots courants sont écartés (ni dans le lexique, ni techniques)."""
    out: set[str] = set()
    for tok in _WORD_RE.findall(strip_html(text or "")):
        low = tok.lower()
        if low.isdigit():
            continue
        stem = low[:-1] if low.endswith("s") and len(low) > 3 else low
        if low in TECH_TERMS:
            out.add(low)
        elif stem in TECH_TERMS:
            out.add(stem)                         # normalise pluriel → singulier
        elif (len(low) >= 3 and low not in STOPWORDS and low not in _EXTRA_STOP
              and _looks_technical(tok)):
            out.add(low)
    return out


def compute(conn, recent_days: int = 7, baseline_days: int = 30, top: int = 12) -> dict:
    rows = db.all_canonical(conn)
    now = datetime.now(timezone.utc)

    recent, baseline = Counter(), Counter()
    example: dict[str, dict] = {}
    sources: dict[str, set] = {}
    hits: dict[str, list[int]] = {}          # term -> ids des articles récents concernés

    for row in rows:
        age = (now - _parse_dt(row)).days
        # Sur title+content (langue d'origine) : le summary est désormais en FR et
        # mélangerait les langues dans l'analyse de fréquence. Content tronqué (coût).
        terms = _terms(f"{row['title']} {(row['content'] or '')[:2000]}")
        if age <= recent_days:
            for t in terms:
                recent[t] += 1
                example.setdefault(t, {"id": row["id"], "title": row["title"]})
                sources.setdefault(t, set()).add(row["source"])
                hits.setdefault(t, []).append(row["id"])
        elif age <= baseline_days:
            for t in terms:
                baseline[t] += 1

    scored = []
    for term, rc in recent.items():
        bc = baseline.get(term, 0)
        lift = (rc + 1) / (bc + 1)          # ratio de montée
        scored.append(
            {
                "term": term,
                "recent": rc,
                "baseline": bc,
                "lift": round(lift, 2),
                "sources": len(sources.get(term, ())),
                "score": rc * lift,
                "example": example.get(term),
                "article_ids": hits.get(term, [])[-12:][::-1],  # jusqu'à 12, plus récents d'abord
            }
        )

    # Tendances : termes récurrents, corroborés par ≥ 2 sources, triés par montée.
    trends = sorted(
        (d for d in scored if d["recent"] >= 2 and d["sources"] >= 2),
        key=lambda d: d["score"],
        reverse=True,
    )[:top]

    # Signaux faibles : émergents (absents de la baseline, 1-2 mentions récentes).
    weak = sorted(
        (d for d in scored if d["baseline"] == 0 and 1 <= d["recent"] <= 2),
        key=lambda d: (d["sources"], d["recent"]),
        reverse=True,
    )[:top]

    return {"trends": trends, "weak": weak, "recent_days": recent_days}
