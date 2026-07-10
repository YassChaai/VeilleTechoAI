"""Connexion et requêtes SQLite. Aucun ORM : `sqlite3` brut."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_db_path() -> str:
    return os.getenv("VEILLE_DB", "data/veille.db")


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Ouvre (et crée si besoin) la base. Retourne des lignes façon dict."""
    db_path = db_path or get_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Attend jusqu'à 5 s si la base est verrouillée (tâches de fond + serveur concurrents).
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    _migrate(conn)
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    """Ajoute les colonnes introduites après coup aux bases existantes."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(articles)")}
    for col, decl in (
        ("authority", "REAL DEFAULT 0"),
        ("relevance", "REAL DEFAULT 0"),
        ("takeaways", "TEXT"),
        ("title_fr", "TEXT"),
    ):
        if col not in cols:
            conn.execute(f"ALTER TABLE articles ADD COLUMN {col} {decl}")


# --- Ingestion --------------------------------------------------------------

def insert_article(conn: sqlite3.Connection, art: dict) -> int:
    """INSERT OR IGNORE sur `url` (UNIQUE). Retourne 1 si inséré, 0 si doublon.

    `art` doit contenir : source, url, title, title_normalized, content,
    category, published_at ; optionnel : authority.
    """
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO articles
            (source, url, title, title_normalized, content, category,
             published_at, authority)
        VALUES
            (:source, :url, :title, :title_normalized, :content, :category,
             :published_at, :authority)
        """,
        {
            "source": art["source"],
            "url": art["url"],
            "title": art["title"],
            "title_normalized": art["title_normalized"],
            "content": art.get("content", ""),
            "category": art.get("category"),
            "published_at": art.get("published_at", ""),
            "authority": float(art.get("authority") or 0.0),
        },
    )
    conn.commit()
    return cur.rowcount


# --- Déduplication ----------------------------------------------------------

def canonical_articles(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Articles non encore marqués comme doublons, du plus ancien au plus récent."""
    return conn.execute(
        """
        SELECT id, title, title_normalized, published_at, ingested_at
        FROM articles
        WHERE duplicate_of_id IS NULL
        ORDER BY id ASC
        """
    ).fetchall()


def set_duplicate(conn: sqlite3.Connection, article_id: int, canonical_id: int) -> None:
    conn.execute(
        "UPDATE articles SET duplicate_of_id = ? WHERE id = ?",
        (canonical_id, article_id),
    )
    conn.commit()


def count_duplicates(conn: sqlite3.Connection, canonical_id: int) -> int:
    """Nombre d'articles rattachés (sources croisées) à un article canonique."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM articles WHERE duplicate_of_id = ?",
        (canonical_id,),
    ).fetchone()
    return row["n"]


def duplicate_counts(conn: sqlite3.Connection) -> dict[int, int]:
    """{canonical_id: nb de doublons rattachés} en une seule requête (évite le N+1)."""
    rows = conn.execute(
        """
        SELECT duplicate_of_id AS cid, COUNT(*) AS n
        FROM articles
        WHERE duplicate_of_id IS NOT NULL
        GROUP BY duplicate_of_id
        """
    ).fetchall()
    return {row["cid"]: row["n"] for row in rows}


# --- Résumé / catégorisation ------------------------------------------------

def articles_without_summary(conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, title, content, category
        FROM articles
        WHERE summary IS NULL
        ORDER BY id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def update_enrichment(
    conn: sqlite3.Connection,
    article_id: int,
    summary: str,
    category: str,
    takeaways: list[str],
) -> None:
    """Enregistre résumé, catégorie et points à retenir (1 par ligne)."""
    conn.execute(
        "UPDATE articles SET summary = ?, category = ?, takeaways = ? WHERE id = ?",
        (summary, category, "\n".join(takeaways or []), article_id),
    )
    conn.commit()


# --- Traduction FR des titres (affichage) ----------------------------------

def articles_without_title_fr(conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    """Articles canoniques dont le titre n'a pas encore été traduit en français."""
    return conn.execute(
        """
        SELECT id, title FROM articles
        WHERE title_fr IS NULL AND duplicate_of_id IS NULL
        ORDER BY id ASC LIMIT ?
        """,
        (limit,),
    ).fetchall()


def update_title_fr(conn: sqlite3.Connection, article_id: int, title_fr: str) -> None:
    conn.execute(
        "UPDATE articles SET title_fr = ? WHERE id = ?", (title_fr, article_id)
    )
    conn.commit()


# --- Restitution (dashboard) ------------------------------------------------

def get_articles(
    conn: sqlite3.Connection,
    domain: str | None = None,
    query: str | None = None,
    sort: str = "date",
    limit: int = 500,
) -> list[sqlite3.Row]:
    """Articles canoniques, filtrés par domaine et/ou recherche texte.

    `sort` : "date" (défaut) ou "relevance" (bonus score de pertinence enrichi).
    """
    sql = [
        "SELECT * FROM articles WHERE duplicate_of_id IS NULL",
    ]
    params: list = []
    if domain:
        sql.append("AND category = ?")
        params.append(domain)
    if query:
        sql.append("AND (title LIKE ? OR summary LIKE ? OR content LIKE ?)")
        like = f"%{query}%"
        params += [like, like, like]
    date_expr = "COALESCE(NULLIF(published_at, ''), ingested_at)"
    if sort == "relevance":
        sql.append(f"ORDER BY relevance DESC, {date_expr} DESC LIMIT ?")
    else:
        sql.append(f"ORDER BY {date_expr} DESC LIMIT ?")
    params.append(limit)
    return conn.execute(" ".join(sql), params).fetchall()


def get_articles_since(conn: sqlite3.Connection, days: int = 7) -> list[sqlite3.Row]:
    """Articles canoniques des `days` derniers jours (pour le digest)."""
    return conn.execute(
        """
        SELECT * FROM articles
        WHERE duplicate_of_id IS NULL
          AND COALESCE(NULLIF(published_at, ''), ingested_at)
              >= datetime('now', ?)
        ORDER BY COALESCE(NULLIF(published_at, ''), ingested_at) DESC
        """,
        (f"-{days} days",),
    ).fetchall()


# --- Digests hebdomadaires (historique) ------------------------------------

def articles_for_week(conn: sqlite3.Connection, week_start: str,
                      week_end: str) -> list[sqlite3.Row]:
    """Articles canoniques publiés/ingérés dans la semaine [week_start, week_end]."""
    return conn.execute(
        """
        SELECT * FROM articles
        WHERE duplicate_of_id IS NULL
          AND date(COALESCE(NULLIF(published_at, ''), ingested_at)) BETWEEN ? AND ?
        ORDER BY category, relevance DESC,
                 COALESCE(NULLIF(published_at, ''), ingested_at) DESC
        """,
        (week_start, week_end),
    ).fetchall()


def upsert_digest(conn: sqlite3.Connection, week_start: str, week_end: str,
                  content: str, article_count: int, model: str) -> None:
    """Enregistre (ou remplace) le digest d'une semaine (clé = week_start)."""
    conn.execute(
        """
        INSERT INTO digests (week_start, week_end, content, article_count, model, generated_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(week_start) DO UPDATE SET
            week_end = excluded.week_end,
            content = excluded.content,
            article_count = excluded.article_count,
            model = excluded.model,
            generated_at = excluded.generated_at
        """,
        (week_start, week_end, content, article_count, model),
    )
    conn.commit()


def get_digest(conn: sqlite3.Connection, week_start: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM digests WHERE week_start = ?", (week_start,)
    ).fetchone()


def list_digests(conn: sqlite3.Connection, days: int = 31) -> list[sqlite3.Row]:
    """Digests du dernier mois, du plus récent au plus ancien."""
    return conn.execute(
        "SELECT * FROM digests WHERE week_start >= date('now', ?) ORDER BY week_start DESC",
        (f"-{days} days",),
    ).fetchall()


def get_by_ids(conn: sqlite3.Connection, ids: list[int]) -> list[sqlite3.Row]:
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT * FROM articles WHERE id IN ({placeholders})", ids
    ).fetchall()
    order = {aid: i for i, aid in enumerate(ids)}
    return sorted(rows, key=lambda r: order.get(r["id"], 1e9))


def count_articles(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM articles").fetchone()["n"]


def reset_articles(conn: sqlite3.Connection, full: bool = False) -> int:
    """Vide les articles et leurs données liées (lectures, enregistrements, digests).
    `full=True` : vide AUSSI comptes, dossiers, préférences et sources. Retourne le
    nombre d'articles supprimés. Ordre imposé par les clés étrangères."""
    n = count_articles(conn)
    conn.execute("UPDATE articles SET duplicate_of_id = NULL")   # casse l'auto-référence
    conn.execute("DELETE FROM read_state")
    conn.execute("DELETE FROM saved_articles")
    conn.execute("DELETE FROM digests")
    conn.execute("DELETE FROM articles")
    conn.execute("DELETE FROM sqlite_sequence WHERE name = 'articles'")  # ids repartent à 1
    if full:
        conn.execute("DELETE FROM folders")
        conn.execute("DELETE FROM preferences")
        conn.execute("DELETE FROM users")
        conn.execute("DELETE FROM sources")
        conn.execute("DELETE FROM profile")
        conn.execute("DELETE FROM sqlite_sequence")
    conn.commit()
    return n


def purge_unsummarized(conn: sqlite3.Connection) -> int:
    """Supprime les articles sans résumé et nettoie les références.

    Invariant : la base ne contient que des articles résumés (plus de « en attente »).
    On annule d'abord les `duplicate_of_id` pointant vers des articles supprimés (sinon
    la clé étrangère bloque la suppression), puis on purge les états lu/enregistré orphelins.
    Retourne le nombre d'articles supprimés.
    """
    n = conn.execute(
        "SELECT COUNT(*) AS n FROM articles WHERE summary IS NULL OR summary = ''"
    ).fetchone()["n"]
    if not n:
        return 0
    doomed = "SELECT id FROM articles WHERE summary IS NULL OR summary = ''"
    # Ordre imposé par les FK (foreign_keys=ON) : d'abord les lignes enfant qui
    # référencent ces articles (read_state, saved_articles), puis les auto-références
    # duplicate_of_id, enfin les articles eux-mêmes.
    conn.execute(f"DELETE FROM read_state WHERE article_id IN ({doomed})")
    conn.execute(f"DELETE FROM saved_articles WHERE article_id IN ({doomed})")
    conn.execute(f"UPDATE articles SET duplicate_of_id = NULL WHERE duplicate_of_id IN ({doomed})")
    conn.execute("DELETE FROM articles WHERE summary IS NULL OR summary = ''")
    conn.commit()
    return n


_FR_ACCENTS = "éèêëàâäçùûüîïôöœ"


def reset_untranslated_summaries(conn: sqlite3.Connection) -> int:
    """Repasse en attente (summary NULL) les résumés SANS aucun accent français.

    En pratique : le repli extractif anglais, produit quand Ollama était indisponible.
    Ils seront re-vulgarisés en français au prochain run (Ollama requis). Heuristique :
    un vrai résumé FR de plusieurs phrases contient forcément des accents. Retourne le
    nombre de résumés remis en attente.
    """
    no_accent = " AND ".join(f"summary NOT LIKE '%{c}%'" for c in _FR_ACCENTS)
    cur = conn.execute(
        "UPDATE articles SET summary = NULL, takeaways = NULL "
        f"WHERE summary IS NOT NULL AND summary <> '' AND ({no_accent})"
    )
    conn.commit()
    return cur.rowcount


def get_article(conn: sqlite3.Connection, article_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM articles WHERE id = ?", (article_id,)
    ).fetchone()


def get_duplicates(conn: sqlite3.Connection, canonical_id: int) -> list[sqlite3.Row]:
    """Articles rattachés à un canonique (mêmes sujet, autres sources)."""
    return conn.execute(
        "SELECT source, url, title FROM articles WHERE duplicate_of_id = ?",
        (canonical_id,),
    ).fetchall()


# --- Profil (bonus personnalisation) ---------------------------------------

def get_profile_keywords(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT keywords FROM profile WHERE id = 1").fetchone()
    return row["keywords"] if row and row["keywords"] else ""


def set_profile_keywords(conn: sqlite3.Connection, keywords: str) -> None:
    conn.execute(
        """
        INSERT INTO profile (id, keywords, updated_at)
        VALUES (1, ?, datetime('now'))
        ON CONFLICT(id) DO UPDATE SET keywords = excluded.keywords,
                                      updated_at = excluded.updated_at
        """,
        (keywords,),
    )
    conn.commit()


# --- Comptes utilisateurs ---------------------------------------------------

def create_user(conn: sqlite3.Connection, username: str, password_hash: str) -> int | None:
    """Crée un compte. Retourne l'id, ou None si le nom est déjà pris."""
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None


def get_user_by_username(conn: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()


def get_user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def update_password(conn: sqlite3.Connection, user_id: int, password_hash: str) -> None:
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id)
    )
    conn.commit()


def delete_user(conn: sqlite3.Connection, user_id: int) -> None:
    """Supprime le compte et toutes ses données (préférences, lu, dossiers, sauvegardes)."""
    for sql in (
        "DELETE FROM saved_articles WHERE user_id = ?",
        "DELETE FROM folders WHERE user_id = ?",
        "DELETE FROM read_state WHERE user_id = ?",
        "DELETE FROM preferences WHERE user_id = ?",
        "DELETE FROM users WHERE id = ?",
    ):
        conn.execute(sql, (user_id,))
    conn.commit()


# --- Préférences par utilisateur -------------------------------------------

def get_preferences(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT keywords, hide_read FROM preferences WHERE user_id = ?", (user_id,)
    ).fetchone()


def set_preferences(conn: sqlite3.Connection, user_id: int, keywords: str,
                    hide_read: bool) -> None:
    conn.execute(
        """
        INSERT INTO preferences (user_id, keywords, hide_read, updated_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(user_id) DO UPDATE SET keywords = excluded.keywords,
                                           hide_read = excluded.hide_read,
                                           updated_at = excluded.updated_at
        """,
        (user_id, keywords, 1 if hide_read else 0),
    )
    conn.commit()


# --- Articles lus / non lus ------------------------------------------------

def mark_read(conn: sqlite3.Connection, user_id: int, article_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO read_state (user_id, article_id) VALUES (?, ?)",
        (user_id, article_id),
    )
    conn.commit()


def mark_unread(conn: sqlite3.Connection, user_id: int, article_id: int) -> None:
    conn.execute(
        "DELETE FROM read_state WHERE user_id = ? AND article_id = ?",
        (user_id, article_id),
    )
    conn.commit()


def read_ids(conn: sqlite3.Connection, user_id: int) -> set[int]:
    return {
        r["article_id"]
        for r in conn.execute(
            "SELECT article_id FROM read_state WHERE user_id = ?", (user_id,)
        ).fetchall()
    }


# --- Dossiers thématiques + « à lire plus tard » ---------------------------

def create_folder(conn: sqlite3.Connection, user_id: int, name: str) -> int | None:
    name = (name or "").strip()
    if not name:
        return None
    try:
        cur = conn.execute(
            "INSERT INTO folders (user_id, name) VALUES (?, ?)", (user_id, name)
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None  # dossier déjà existant pour cet utilisateur


def list_folders(conn: sqlite3.Connection, user_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM folders WHERE user_id = ? ORDER BY name", (user_id,)
    ).fetchall()


def get_folder(conn: sqlite3.Connection, user_id: int, folder_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM folders WHERE id = ? AND user_id = ?", (folder_id, user_id)
    ).fetchone()


def delete_folder(conn: sqlite3.Connection, user_id: int, folder_id: int) -> None:
    """Supprime un dossier ; ses articles repassent en « à lire » (sans dossier)."""
    conn.execute(
        "UPDATE saved_articles SET folder_id = NULL WHERE user_id = ? AND folder_id = ?",
        (user_id, folder_id),
    )
    conn.execute(
        "DELETE FROM folders WHERE id = ? AND user_id = ?", (folder_id, user_id)
    )
    conn.commit()


def save_article(conn: sqlite3.Connection, user_id: int, article_id: int,
                 folder_id: int | None = None) -> None:
    """Enregistre (ou déplace) un article dans un dossier — 1 emplacement par article."""
    conn.execute(
        """
        INSERT INTO saved_articles (user_id, article_id, folder_id, saved_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(user_id, article_id) DO UPDATE SET folder_id = excluded.folder_id,
                                                       saved_at = excluded.saved_at
        """,
        (user_id, article_id, folder_id),
    )
    conn.commit()


def unsave_article(conn: sqlite3.Connection, user_id: int, article_id: int) -> None:
    conn.execute(
        "DELETE FROM saved_articles WHERE user_id = ? AND article_id = ?",
        (user_id, article_id),
    )
    conn.commit()


def saved_ids(conn: sqlite3.Connection, user_id: int) -> set[int]:
    return {
        r["article_id"]
        for r in conn.execute(
            "SELECT article_id FROM saved_articles WHERE user_id = ?", (user_id,)
        ).fetchall()
    }


def get_saved(conn: sqlite3.Connection, user_id: int, article_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM saved_articles WHERE user_id = ? AND article_id = ?",
        (user_id, article_id),
    ).fetchone()


def list_saved(conn: sqlite3.Connection, user_id: int,
               folder_id="__all__") -> list[sqlite3.Row]:
    """Articles sauvegardés. folder_id : '__all__' = tout, None = sans dossier, int = un dossier."""
    sql = [
        "SELECT a.*, sa.folder_id AS sa_folder_id, sa.saved_at AS sa_saved_at",
        "FROM saved_articles sa JOIN articles a ON a.id = sa.article_id",
        "WHERE sa.user_id = ?",
    ]
    params: list = [user_id]
    if folder_id != "__all__":
        if folder_id is None:
            sql.append("AND sa.folder_id IS NULL")
        else:
            sql.append("AND sa.folder_id = ?")
            params.append(folder_id)
    sql.append("ORDER BY sa.saved_at DESC")
    return conn.execute(" ".join(sql), params).fetchall()


def folder_counts(conn: sqlite3.Connection, user_id: int) -> dict:
    """{folder_id: nb} des articles sauvegardés (clé None = sans dossier)."""
    rows = conn.execute(
        "SELECT folder_id, COUNT(*) AS n FROM saved_articles WHERE user_id = ? "
        "GROUP BY folder_id",
        (user_id,),
    ).fetchall()
    return {r["folder_id"]: r["n"] for r in rows}


# --- Sources dynamiques (socle + découvertes) ------------------------------

def upsert_source(conn: sqlite3.Connection, src: dict) -> int:
    """INSERT OR IGNORE d'une source (url UNIQUE). Retourne 1 si ajoutée, 0 sinon."""
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO sources (name, type, url, domain, authority, origin)
        VALUES (:name, :type, :url, :domain, :authority, :origin)
        """,
        {
            "name": src["name"],
            "type": src.get("type", "rss"),
            "url": src["url"],
            "domain": src.get("domain"),
            "authority": float(src.get("authority") or 0.5),
            "origin": src.get("origin", "discovered"),
        },
    )
    conn.commit()
    return cur.rowcount


def existing_source_urls(conn: sqlite3.Connection) -> set[str]:
    return {r["url"] for r in conn.execute("SELECT url FROM sources").fetchall()}


def active_discovered_sources(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Sources découvertes encore actives (pour l'union au chargement)."""
    return conn.execute(
        """
        SELECT name, type, url, domain, authority
        FROM sources
        WHERE origin = 'discovered' AND active = 1
        ORDER BY domain, quality DESC
        """
    ).fetchall()


def discovered_sources(conn: sqlite3.Connection, active_only: bool = False) -> list[sqlite3.Row]:
    sql = "SELECT * FROM sources WHERE origin = 'discovered'"
    if active_only:
        sql += " AND active = 1"
    return conn.execute(sql).fetchall()


def list_sources(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Toutes les sources, pour la page /sources."""
    return conn.execute(
        """
        SELECT * FROM sources
        ORDER BY (origin = 'static') DESC, domain, active DESC, quality DESC, name
        """
    ).fetchall()


def set_source_active(conn: sqlite3.Connection, source_id: int, active: bool) -> None:
    conn.execute(
        "UPDATE sources SET active = ? WHERE id = ?", (1 if active else 0, source_id)
    )
    conn.commit()


def update_source_quality(conn: sqlite3.Connection, source_id: int, quality: float) -> None:
    """Enregistre la qualité observée (moyenne mobile) et incrémente le compteur de runs."""
    conn.execute(
        "UPDATE sources SET quality = ?, runs = runs + 1, last_checked = datetime('now') "
        "WHERE id = ?",
        (round(quality, 4), source_id),
    )
    conn.commit()


def update_source_authority(conn: sqlite3.Connection, source_id: int, authority: float) -> None:
    conn.execute(
        "UPDATE sources SET authority = ? WHERE id = ?", (round(authority, 4), source_id)
    )
    conn.commit()


# --- Recherche sémantique (bonus) ------------------------------------------

def articles_without_embedding(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, title, content FROM articles WHERE embedding IS NULL"
    ).fetchall()


def set_embedding(conn: sqlite3.Connection, article_id: int, blob: bytes) -> None:
    conn.execute(
        "UPDATE articles SET embedding = ? WHERE id = ?", (blob, article_id)
    )
    conn.commit()


def all_embeddings(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, embedding FROM articles "
        "WHERE embedding IS NOT NULL AND duplicate_of_id IS NULL"
    ).fetchall()


# --- Score de pertinence enrichi (bonus) -----------------------------------

def canonical_for_ranking(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, authority, published_at, ingested_at
        FROM articles
        WHERE duplicate_of_id IS NULL
        """
    ).fetchall()


def update_relevance(conn: sqlite3.Connection, article_id: int, value: float) -> None:
    conn.execute(
        "UPDATE articles SET relevance = ? WHERE id = ?", (value, article_id)
    )
    conn.commit()


# --- Détection de tendances / signaux faibles (bonus) ----------------------

def all_canonical(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Articles canoniques avec le texte nécessaire à l'analyse de tendances."""
    return conn.execute(
        """
        SELECT id, title, summary, content, source, url, category,
               published_at, ingested_at
        FROM articles
        WHERE duplicate_of_id IS NULL
        """
    ).fetchall()
