-- Schéma SQLite de la plateforme de veille.
-- Idempotent : ré-exécutable sans erreur (CREATE TABLE IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    title_normalized TEXT NOT NULL,
    title_fr TEXT,                       -- titre traduit en français (affichage)
    content TEXT,
    summary TEXT,
    takeaways TEXT,                      -- points à retenir (1 par ligne)
    category TEXT,                       -- Tech / Business de la tech / Data & IA / UX & solutions numériques
    published_at TEXT,
    ingested_at TEXT DEFAULT CURRENT_TIMESTAMP,
    duplicate_of_id INTEGER REFERENCES articles(id),
    authority REAL DEFAULT 0,            -- bonus pertinence : autorité éditoriale de la source
    relevance REAL DEFAULT 0,            -- bonus pertinence : score calculé [0..1]
    embedding BLOB                       -- bonus recherche sémantique, vecteur sérialisé
);

CREATE INDEX IF NOT EXISTS idx_title_norm ON articles(title_normalized);
CREATE INDEX IF NOT EXISTS idx_category ON articles(category);
CREATE INDEX IF NOT EXISTS idx_relevance ON articles(relevance);

CREATE TABLE IF NOT EXISTS profile (     -- bonus personnalisation, un seul profil (pas de multi-user)
    id INTEGER PRIMARY KEY CHECK (id = 1),
    keywords TEXT,                        -- mots-clés/domaines pondérés, JSON
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (       -- comptes (multi-utilisateur)
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS preferences (  -- préférences par utilisateur
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    keywords TEXT,                         -- mots-clés pondérés (réordonne les articles)
    hide_read INTEGER DEFAULT 0,           -- masquer les articles lus par défaut
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS read_state (   -- articles lus par utilisateur
    user_id INTEGER NOT NULL REFERENCES users(id),
    article_id INTEGER NOT NULL REFERENCES articles(id),
    read_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, article_id)
);

CREATE TABLE IF NOT EXISTS folders (      -- dossiers thématiques créés par l'utilisateur
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS saved_articles ( -- « à lire plus tard », 1 article = 1 emplacement
    user_id INTEGER NOT NULL REFERENCES users(id),
    article_id INTEGER NOT NULL REFERENCES articles(id),
    folder_id INTEGER REFERENCES folders(id),   -- NULL = à lire (sans dossier)
    saved_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, article_id)
);

CREATE TABLE IF NOT EXISTS digests (     -- digests éditoriaux hebdomadaires (historique)
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT NOT NULL UNIQUE,      -- lundi (ISO) de la semaine couverte
    week_end TEXT NOT NULL,               -- dimanche (ISO)
    content TEXT NOT NULL,                -- le digest rédigé, en Markdown
    article_count INTEGER DEFAULT 0,      -- nb d'articles couverts
    model TEXT,                           -- backend : Claude | Ollama | dégradé
    generated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_digests_week ON digests(week_start);

CREATE TABLE IF NOT EXISTS sources (     -- sources dynamiques (socle YAML + découvertes)
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,                   -- rss | api
    url TEXT NOT NULL UNIQUE,
    domain TEXT,
    authority REAL DEFAULT 0.5,
    origin TEXT DEFAULT 'discovered',     -- static | discovered
    quality REAL DEFAULT 0,               -- moyenne mobile du rendu qualité observé [0..1]
    active INTEGER DEFAULT 1,             -- 0 = élaguée par la boucle d'auto-ajustement
    runs INTEGER DEFAULT 0,               -- nb de runs évalués (avant élagage)
    added_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_checked TEXT
);
CREATE INDEX IF NOT EXISTS idx_sources_active ON sources(active);
