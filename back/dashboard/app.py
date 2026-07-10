"""Dashboard Flask : liste filtrable + recherche, digest, comptes & perso.

Phase 1 = HTML Jinja rendu côté serveur. Comptes multi-utilisateur (sessions Flask,
mots de passe hachés) : la navigation reste libre sans compte ; se connecter débloque
le suivi lu/non-lu, la lecture-à-plus-tard (dossiers) et les préférences par utilisateur.
"""

from __future__ import annotations

import os
import threading
from collections import defaultdict
from functools import wraps

from dotenv import load_dotenv
from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from ingestion import discovery
from processing import digest as weekly_digest
from processing import semantic_search, source_health, summarize, trends
from processing.summarize import DOMAINS
from storage import db

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-le-guetteur-change-me")

# Mappe les 4 domaines exacts vers un slug CSS (chips catégorie color-codées).
_DOMAIN_SLUGS = {
    "Tech": "tech",
    "Business de la tech": "business",
    "Data & IA": "data",
    "UX & solutions numériques": "ux",
}


# --- Session / helpers ------------------------------------------------------

def _uid():
    return session.get("user_id")


@app.context_processor
def _inject_helpers():
    """Expose `domain_slug()` et l'utilisateur courant à tous les templates."""
    user = None
    if session.get("user_id"):
        user = {"id": session["user_id"], "username": session.get("username")}
    return {
        "domain_slug": lambda category: _DOMAIN_SLUGS.get(category, "none"),
        "current_user": user,
    }


@app.before_request
def _drop_stale_session():
    """Vide la session si elle pointe vers un utilisateur qui n'existe plus (ex. après
    un `reset`). Évite les erreurs de clé étrangère (read_state → users) au mark_read."""
    uid = session.get("user_id")
    if not uid:
        return
    conn = db.get_connection()
    try:
        db.init_db(conn)
        if db.get_user(conn, uid) is None:
            session.clear()
    finally:
        conn.close()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _uid():
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def _back():
    """Retour à la page d'origine (champ `next` relatif, sinon referrer, sinon accueil)."""
    nxt = request.form.get("next")
    if nxt and nxt.startswith("/"):
        return redirect(nxt)
    return redirect(request.referrer or url_for("index"))


def _keyword_score(row, keywords: list[str]) -> int:
    haystack = f"{row['title']} {row['summary'] or ''}".lower()
    return sum(haystack.count(kw) for kw in keywords)


# --- Authentification -------------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if _uid():
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        if len(username) < 3:
            error = "Le nom d'utilisateur doit faire au moins 3 caractères."
        elif len(password) < 6:
            error = "Le mot de passe doit faire au moins 6 caractères."
        elif password != confirm:
            error = "Les deux mots de passe ne correspondent pas."
        else:
            conn = db.get_connection()
            db.init_db(conn)
            uid = db.create_user(conn, username, generate_password_hash(password))
            conn.close()
            if uid is None:
                error = "Ce nom d'utilisateur est déjà pris."
            else:
                session.clear()
                session["user_id"] = uid
                session["username"] = username
                return redirect(url_for("index"))
    return render_template("auth.html", mode="register", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    if _uid():
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        conn = db.get_connection()
        db.init_db(conn)
        user = db.get_user_by_username(conn, username)
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            nxt = request.form.get("next") or request.args.get("next") or ""
            return redirect(nxt if nxt.startswith("/") else url_for("index"))
        error = "Nom d'utilisateur ou mot de passe invalide."
    return render_template("auth.html", mode="login", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("index"))


# --- Articles ---------------------------------------------------------------

@app.route("/")
def index():
    domain = request.args.get("domain") or None
    query = (request.args.get("q") or "").strip() or None
    sort = request.args.get("sort") or "date"
    read_filter = request.args.get("read") or None
    if domain not in DOMAINS:
        domain = None
    if sort not in ("date", "relevance"):
        sort = "date"

    conn = db.get_connection()
    db.init_db(conn)

    # Recherche sémantique (bonus) si activée et requête présente ; sinon SQL LIKE.
    if query and semantic_search.available():
        ids = semantic_search.search(conn, query)
        rows = db.get_by_ids(conn, ids)
        if domain:
            rows = [r for r in rows if r["category"] == domain]
    else:
        rows = db.get_articles(conn, domain=domain, query=query, sort=sort)

    uid = _uid()
    read: set = set()
    saved: set = set()
    if uid:
        read = db.read_ids(conn, uid)
        saved = db.saved_ids(conn, uid)
        pref = db.get_preferences(conn, uid)
        kw_source = (pref["keywords"] if pref and pref["keywords"] else "")
        if read_filter is None and pref and pref["hide_read"]:
            read_filter = "unread"  # préférence : masquer les lus par défaut
    else:
        kw_source = db.get_profile_keywords(conn)
    read_filter = read_filter if read_filter in ("all", "unread", "read") else "all"

    # Réordonnancement par mots-clés (perso) — prioritaire s'il existe.
    keywords = [k.strip().lower() for k in kw_source.split(",") if k.strip()]
    if keywords:
        rows = sorted(rows, key=lambda r: _keyword_score(r, keywords), reverse=True)

    # Lu / non lu : filtre, et par défaut on ne met pas les lus en avant.
    if uid:
        if read_filter == "unread":
            rows = [r for r in rows if r["id"] not in read]
        elif read_filter == "read":
            rows = [r for r in rows if r["id"] in read]
        else:
            rows = sorted(rows, key=lambda r: r["id"] in read)  # non-lus d'abord (tri stable)

    total = db.count_articles(conn)
    conn.close()

    return render_template(
        "index.html",
        articles=rows,
        domains=DOMAINS,
        current_domain=domain,
        query=query or "",
        sort=sort,
        total=total,
        personalized=bool(keywords),
        logged_in=bool(uid),
        read=read,
        saved=saved,
        read_filter=read_filter,
        ingest_running=_ingest_state["running"],
    )


@app.route("/article/<int:article_id>")
def article_detail(article_id: int):
    """Page de synthèse : résumé + points à retenir + lien officiel. Marque lu à l'ouverture."""
    conn = db.get_connection()
    db.init_db(conn)
    article = db.get_article(conn, article_id)
    if article is None:
        conn.close()
        abort(404)
    dupes = db.get_duplicates(conn, article_id)

    uid = _uid()
    is_read = False
    saved = None
    folders = []
    saved_folder_name = None
    if uid:
        db.mark_read(conn, uid, article_id)  # ouverture = lu
        is_read = True
        saved = db.get_saved(conn, uid, article_id)
        folders = db.list_folders(conn, uid)
        if saved and saved["folder_id"]:
            saved_folder_name = next(
                (f["name"] for f in folders if f["id"] == saved["folder_id"]), None
            )
    conn.close()

    takeaways = [t for t in (article["takeaways"] or "").split("\n") if t.strip()]
    return render_template(
        "detail.html",
        a=article,
        takeaways=takeaways,
        dupes=dupes,
        crossed=len(dupes),
        logged_in=bool(uid),
        is_read=is_read,
        saved=saved,
        saved_folder_name=saved_folder_name,
        folders=folders,
    )


@app.route("/articles/<int:article_id>/read", methods=["POST"])
@login_required
def toggle_read(article_id: int):
    conn = db.get_connection()
    db.init_db(conn)
    if request.form.get("action") == "unread":
        db.mark_unread(conn, _uid(), article_id)
    else:
        db.mark_read(conn, _uid(), article_id)
    conn.close()
    return _back()


# --- Chercher de nouveaux articles (pipeline en arrière-plan) ---------------

_ingest_state = {
    "running": False, "done": False, "percent": 0, "phase": "",
    "ingested": 0, "summarized": 0,
}


def _reset_ingest_state() -> None:
    _ingest_state.update({
        "running": False, "done": False, "percent": 0, "phase": "",
        "ingested": 0, "summarized": 0,
    })


def _mask_key(key: str | None) -> str | None:
    """Indice masqué d'une clé (jamais la clé complète côté client)."""
    if not key:
        return None
    return f"…{key[-4:]}" if len(key) > 4 else "…"


def _session_pipeline_kwargs(conn) -> dict:
    """Paramètres du pipeline selon le compte déclencheur (BYOK) :
      - clé présente        → mode Claude (api_key + modèle du compte) ;
      - connecté sans clé    → mode gratuit : tente Ollama (FR), sinon extractif (EN) ;
      - invité / build (CLI) → {} → valeurs d'environnement.
    """
    uid = _uid()
    if not uid:
        return {}
    key = db.get_user_api_key(conn, uid)
    if key:
        return {"api_key": key, "model": db.get_user_model(conn, uid)}
    return {"translate_backend": "auto", "require_llm": False}


def _run_ingest(pipeline_kwargs=None) -> None:
    """Relance le pipeline complet en tâche de fond, avec suivi de progression.

    `pipeline_kwargs` : paramètres résolus depuis le compte déclencheur (voir
    `_session_pipeline_kwargs`).
    """
    import main  # import paresseux : évite d'exécuter le module au chargement de l'app
    try:
        main.run_pipeline(
            on_progress=lambda info: _ingest_state.update(info),
            **(pipeline_kwargs or {}),
        )
    except Exception as exc:
        _ingest_state.update({"percent": 100, "phase": f"Erreur : {exc}"})
    finally:
        _ingest_state["running"] = False
        _ingest_state["done"] = True


@app.route("/articles/refresh", methods=["POST"])
def articles_refresh():
    """Va chercher de nouveaux articles dans les sources existantes (ingestion + résumé)."""
    conn = db.get_connection()
    db.init_db(conn)
    kwargs = _session_pipeline_kwargs(conn)
    conn.close()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        if not _ingest_state["running"]:
            _reset_ingest_state()
            _ingest_state["running"] = True
            _ingest_state["phase"] = "Démarrage…"
            threading.Thread(target=_run_ingest, args=(kwargs,), daemon=True).start()
        return jsonify({"started": True})
    import main  # sans JS : exécution synchrone puis redirection
    main.run_pipeline(**kwargs)
    return redirect(url_for("index"))


@app.route("/articles/refresh/status")
def articles_refresh_status():
    return jsonify({k: _ingest_state[k] for k in (
        "running", "done", "percent", "phase", "ingested", "summarized",
    )})


# --- Lecture à plus tard / dossiers ----------------------------------------

@app.route("/save/<int:article_id>", methods=["POST"])
@login_required
def save(article_id: int):
    uid = _uid()
    folder_raw = request.form.get("folder_id")
    new_folder = (request.form.get("new_folder") or "").strip()
    conn = db.get_connection()
    db.init_db(conn)
    folder_id = None
    if new_folder:
        folder_id = db.create_folder(conn, uid, new_folder)
        if folder_id is None:  # déjà existant → on le réutilise
            match = next((f for f in db.list_folders(conn, uid)
                          if f["name"].lower() == new_folder.lower()), None)
            folder_id = match["id"] if match else None
    elif folder_raw and folder_raw.isdigit():
        folder = db.get_folder(conn, uid, int(folder_raw))
        folder_id = folder["id"] if folder else None
    db.save_article(conn, uid, article_id, folder_id)
    conn.close()
    return _back()


@app.route("/unsave/<int:article_id>", methods=["POST"])
@login_required
def unsave(article_id: int):
    conn = db.get_connection()
    db.init_db(conn)
    db.unsave_article(conn, _uid(), article_id)
    conn.close()
    return _back()


@app.route("/library")
@login_required
def library():
    conn = db.get_connection()
    db.init_db(conn)
    uid = _uid()
    folders = db.list_folders(conn, uid)
    counts = db.folder_counts(conn, uid)
    unfiled = db.list_saved(conn, uid, folder_id=None)
    by_folder = {f["id"]: db.list_saved(conn, uid, folder_id=f["id"]) for f in folders}
    read = db.read_ids(conn, uid)
    total = sum(counts.values())
    conn.close()
    return render_template(
        "library.html",
        folders=folders, counts=counts, unfiled=unfiled,
        by_folder=by_folder, read=read, total=total,
    )


@app.route("/folders/create", methods=["POST"])
@login_required
def folder_create():
    db_conn = db.get_connection()
    db.init_db(db_conn)
    db.create_folder(db_conn, _uid(), request.form.get("name") or "")
    db_conn.close()
    return redirect(url_for("library"))


@app.route("/folders/<int:folder_id>/delete", methods=["POST"])
@login_required
def folder_delete(folder_id: int):
    conn = db.get_connection()
    db.init_db(conn)
    db.delete_folder(conn, _uid(), folder_id)
    conn.close()
    return redirect(url_for("library"))


# --- Tendances / sources / digest ------------------------------------------

@app.route("/trends")
def trends_view():
    """Bonus : tendances et signaux faibles des derniers jours."""
    conn = db.get_connection()
    db.init_db(conn)
    data = trends.compute(conn)
    conn.close()
    return render_template("trends.html", **data)


# État partagé de la découverte en arrière-plan (un seul rafraîchissement à la fois).
_refresh_state = {
    "running": False, "done": False, "percent": 0, "phase": "",
    "found": 0, "validated": 0, "kept": 0, "added": 0, "removed": 0, "active": 0,
}


def _reset_refresh_state() -> None:
    _refresh_state.update({
        "running": False, "done": False, "percent": 0, "phase": "",
        "found": 0, "validated": 0, "kept": 0, "added": 0, "removed": 0, "active": 0,
    })


def _run_refresh() -> None:
    """Découverte + dédoublonnage, en tâche de fond, avec mise à jour de la progression."""
    try:
        conn = db.get_connection()
        db.init_db(conn)
        candidates = discovery.discover(
            db.existing_source_urls(conn),
            on_progress=lambda info: _refresh_state.update(info),
        )
        added = sum(db.upsert_source(conn, c) for c in candidates)
        removed = source_health.dedupe_sources(conn)
        active = len(db.active_discovered_sources(conn))
        conn.close()
        _refresh_state.update({"added": added, "removed": removed, "active": active,
                               "percent": 100, "phase": "Terminé"})
    except Exception as exc:  # on remonte l'erreur à l'UI
        _refresh_state.update({"percent": 100, "phase": f"Erreur : {exc}"})
    finally:
        _refresh_state["running"] = False
        _refresh_state["done"] = True


@app.route("/sources")
def sources_view():
    """Bonus : sources actives — socle + découvertes autonomes (autorité, qualité, état)."""
    conn = db.get_connection()
    db.init_db(conn)
    rows = db.list_sources(conn)
    conn.close()
    return render_template(
        "sources.html",
        sources=rows,
        discovery_enabled=discovery.enabled(),
        refreshed=request.args.get("refreshed"),
        refresh_running=_refresh_state["running"],
    )


@app.route("/sources/refresh", methods=["POST"])
def sources_refresh():
    """Rafraîchit les sources. En AJAX : lance la découverte en fond (suivi via /status).
    Sans JS : exécution synchrone puis redirection."""
    if not discovery.enabled():
        return redirect(url_for("sources_view", refreshed="off"))

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        if not _refresh_state["running"]:
            _reset_refresh_state()
            _refresh_state["running"] = True
            _refresh_state["phase"] = "Démarrage…"
            threading.Thread(target=_run_refresh, daemon=True).start()
        return jsonify({"started": True})

    conn = db.get_connection()
    db.init_db(conn)
    candidates = discovery.discover(db.existing_source_urls(conn))
    added = sum(db.upsert_source(conn, c) for c in candidates)
    source_health.dedupe_sources(conn)
    conn.close()
    return redirect(url_for("sources_view", refreshed=added))


@app.route("/sources/refresh/status")
def sources_refresh_status():
    """Progression du rafraîchissement en cours (JSON, interrogé par la page)."""
    return jsonify({k: _refresh_state[k] for k in (
        "running", "done", "percent", "phase",
        "found", "validated", "kept", "added", "removed", "active",
    )})


@app.route("/digest")
def digest():
    """Bonus : temps forts des 7 derniers jours, groupés par domaine."""
    conn = db.get_connection()
    db.init_db(conn)
    rows = db.get_articles_since(conn, days=7)
    counts = db.duplicate_counts(conn)  # 1 requête au lieu d'un COUNT par article

    grouped: dict[str, list] = defaultdict(list)
    for row in rows:
        crossed = counts.get(row["id"], 0)
        grouped[row["category"] or "Autres"].append((crossed, row))

    digest_data = {}
    for domain in DOMAINS:
        items = grouped.get(domain, [])
        items.sort(key=lambda t: t[0], reverse=True)
        if items:
            digest_data[domain] = items
    conn.close()

    return render_template("digest.html", digest=digest_data, domains=DOMAINS)


# --- Préférences ------------------------------------------------------------

@app.route("/settings", methods=["GET", "POST"])
def settings():
    """Préférences : par utilisateur si connecté, sinon profil unique (invité)."""
    conn = db.get_connection()
    db.init_db(conn)
    uid = _uid()

    if request.method == "POST":
        keywords = (request.form.get("keywords") or "").strip()
        if uid:
            db.set_preferences(conn, uid, keywords, request.form.get("hide_read") == "on")
        else:
            db.set_profile_keywords(conn, keywords)
        conn.close()
        return redirect(url_for("settings", saved=1))

    if uid:
        pref = db.get_preferences(conn, uid)
        keywords = pref["keywords"] if pref and pref["keywords"] else ""
        hide_read = bool(pref["hide_read"]) if pref else False
    else:
        keywords = db.get_profile_keywords(conn)
        hide_read = False
    conn.close()
    return render_template(
        "settings.html",
        keywords=keywords,
        hide_read=hide_read,
        saved=request.args.get("saved"),
        logged_in=bool(uid),
    )


# --- Mon compte -------------------------------------------------------------

def _account_stats(conn, uid) -> dict:
    return {
        "read": len(db.read_ids(conn, uid)),
        "saved": len(db.saved_ids(conn, uid)),
        "folders": len(db.list_folders(conn, uid)),
    }


@app.route("/account")
@login_required
def account():
    conn = db.get_connection()
    db.init_db(conn)
    uid = _uid()
    user = db.get_user(conn, uid)
    stats = _account_stats(conn, uid)
    conn.close()
    return render_template(
        "account.html", user=user, stats=stats,
        msg=request.args.get("msg"), error=None,
    )


@app.route("/account/password", methods=["POST"])
@login_required
def account_password():
    uid = _uid()
    current = request.form.get("current") or ""
    new = request.form.get("new") or ""
    confirm = request.form.get("confirm") or ""
    conn = db.get_connection()
    db.init_db(conn)
    user = db.get_user(conn, uid)

    error = None
    if not check_password_hash(user["password_hash"], current):
        error = "Mot de passe actuel incorrect."
    elif len(new) < 6:
        error = "Le nouveau mot de passe doit faire au moins 6 caractères."
    elif new != confirm:
        error = "Les deux nouveaux mots de passe ne correspondent pas."

    if error is None:
        db.update_password(conn, uid, generate_password_hash(new))
        conn.close()
        return redirect(url_for("account", msg="pwd"))

    stats = _account_stats(conn, uid)
    conn.close()
    return render_template("account.html", user=user, stats=stats, msg=None, error=error)


@app.route("/account/delete", methods=["POST"])
@login_required
def account_delete():
    conn = db.get_connection()
    db.init_db(conn)
    db.delete_user(conn, _uid())
    conn.close()
    session.clear()
    return redirect(url_for("index"))


# ===========================================================================
#  API JSON — Phase 2 (front Next.js)
#
#  Mêmes données, mêmes règles métier que les routes HTML ci-dessus, mais en
#  JSON. Le front Next (port 3000) proxifie /api vers Flask (port 5000) → une
#  seule origine, la session Flask (cookie) fonctionne sans CORS. Les routes
#  HTML Jinja restent en parallèle : couper Next et rouvrir le dashboard Jinja
#  doit toujours marcher (critère d'acceptation Phase 2).
# ===========================================================================

def _payload():
    """Corps de requête : JSON en priorité, repli sur le form classique."""
    return request.get_json(silent=True) or request.form


def _api_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _uid():
            return jsonify({"error": "auth_required"}), 401
        return view(*args, **kwargs)
    return wrapped


def _user_json():
    if not _uid():
        return None
    return {"id": session["user_id"], "username": session.get("username")}


def _excerpt(row, limit: int = 220) -> str:
    text = (row["summary"] or row["content"] or "")
    first = text.split("\n")[0].strip()
    return (first[: limit - 1] + "…") if len(first) > limit else first


def _article_json(row, *, read=None, saved=None, takeaways=False) -> dict:
    title_fr = row["title_fr"] if "title_fr" in row.keys() else None
    d = {
        "id": row["id"],
        "source": row["source"],
        "url": row["url"],
        "title": title_fr or row["title"],
        "title_original": row["title"],
        "category": row["category"],
        "domain_slug": _DOMAIN_SLUGS.get(row["category"], "none"),
        "summary": row["summary"],
        "excerpt": _excerpt(row),
        "published_at": row["published_at"],
        "ingested_at": row["ingested_at"],
        "relevance": row["relevance"],
    }
    if read is not None:
        d["read"] = row["id"] in read
    if saved is not None:
        d["saved"] = row["id"] in saved
    if takeaways:
        d["takeaways"] = [t for t in (row["takeaways"] or "").split("\n") if t.strip()]
    return d


def _source_json(row) -> dict:
    keys = ("id", "name", "type", "url", "domain", "authority", "origin",
            "quality", "active", "runs", "added_at", "last_checked")
    d = {k: (row[k] if k in row.keys() else None) for k in keys}
    d["domain_slug"] = _DOMAIN_SLUGS.get(row["domain"], "none")
    d["active"] = bool(d["active"])
    return d


# --- Méta / session ---------------------------------------------------------

@app.route("/api/meta")
def api_meta():
    return jsonify({
        "app": "Le Guetteur",
        "domains": DOMAINS,
        "discovery_enabled": discovery.enabled(),
        "semantic": semantic_search.available(),
        "ingest_running": _ingest_state["running"],
    })


@app.route("/api/ai-status")
def api_ai_status():
    """Ce que le serveur peut faire pour résumer (onboarding) : Ollama local détecté ?
    modèles Claude proposés ? clé serveur présente ?"""
    from processing import translate
    st = translate.ollama_status()
    return jsonify({
        "ollama_up": st["up"],                # daemon Ollama joignable
        "ollama_has_model": st["has_model"],  # modèle requis téléchargé
        "ollama_available": st["available"],  # prêt = daemon + modèle
        "ollama_model": st["model"],
        "has_env_key": bool(os.getenv("ANTHROPIC_API_KEY")),
        "models": summarize.MODEL_CHOICES,
    })


@app.route("/api/session")
def api_session():
    return jsonify({"user": _user_json()})


@app.route("/api/register", methods=["POST"])
def api_register():
    if _uid():
        return jsonify({"error": "already_logged_in"}), 400
    data = _payload()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    confirm = data.get("confirm") or ""
    key = (data.get("key") or "").strip()      # BYOK optionnel dès l'inscription
    model = (data.get("model") or "").strip()  # modèle Claude choisi, optionnel
    if len(username) < 3:
        return jsonify({"error": "Le nom d'utilisateur doit faire au moins 3 caractères."}), 400
    if len(password) < 6:
        return jsonify({"error": "Le mot de passe doit faire au moins 6 caractères."}), 400
    if password != confirm:
        return jsonify({"error": "Les deux mots de passe ne correspondent pas."}), 400
    if key and not key.startswith("sk-ant-"):
        return jsonify({"error": "Clé API : format inattendu (elle commence par « sk-ant- »). "
                                 "Laisse le champ vide pour l'ajouter plus tard."}), 400
    if model and model not in {m["id"] for m in summarize.MODEL_CHOICES}:
        return jsonify({"error": "Modèle inconnu."}), 400
    conn = db.get_connection()
    db.init_db(conn)
    uid = db.create_user(conn, username, generate_password_hash(password))
    if uid is None:
        conn.close()
        return jsonify({"error": "Ce nom d'utilisateur est déjà pris."}), 400
    if key:
        db.set_user_api_key(conn, uid, key)
    if model:
        db.set_user_model(conn, uid, model)
    conn.close()
    session.clear()
    session["user_id"] = uid
    session["username"] = username
    return jsonify({"user": _user_json()})


@app.route("/api/login", methods=["POST"])
def api_login():
    if _uid():
        return jsonify({"error": "already_logged_in"}), 400
    data = _payload()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    conn = db.get_connection()
    db.init_db(conn)
    user = db.get_user_by_username(conn, username)
    conn.close()
    if user and check_password_hash(user["password_hash"], password):
        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        return jsonify({"user": _user_json()})
    return jsonify({"error": "Nom d'utilisateur ou mot de passe invalide."}), 401


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


# --- Articles ---------------------------------------------------------------

@app.route("/api/articles")
def api_articles():
    domain = request.args.get("domain") or None
    query = (request.args.get("q") or "").strip() or None
    sort = request.args.get("sort") or "date"
    read_filter = request.args.get("read") or None
    if domain not in DOMAINS:
        domain = None
    if sort not in ("date", "relevance"):
        sort = "date"

    conn = db.get_connection()
    db.init_db(conn)

    if query and semantic_search.available():
        ids = semantic_search.search(conn, query)
        rows = db.get_by_ids(conn, ids)
        if domain:
            rows = [r for r in rows if r["category"] == domain]
    else:
        rows = db.get_articles(conn, domain=domain, query=query, sort=sort)

    uid = _uid()
    read: set = set()
    saved: set = set()
    if uid:
        read = db.read_ids(conn, uid)
        saved = db.saved_ids(conn, uid)
        pref = db.get_preferences(conn, uid)
        kw_source = (pref["keywords"] if pref and pref["keywords"] else "")
        if read_filter is None and pref and pref["hide_read"]:
            read_filter = "unread"
    else:
        kw_source = db.get_profile_keywords(conn)
    read_filter = read_filter if read_filter in ("all", "unread", "read") else "all"

    keywords = [k.strip().lower() for k in kw_source.split(",") if k.strip()]
    if keywords:
        rows = sorted(rows, key=lambda r: _keyword_score(r, keywords), reverse=True)

    if uid:
        if read_filter == "unread":
            rows = [r for r in rows if r["id"] not in read]
        elif read_filter == "read":
            rows = [r for r in rows if r["id"] in read]
        else:
            rows = sorted(rows, key=lambda r: r["id"] in read)

    total = db.count_articles(conn)
    conn.close()

    return jsonify({
        "articles": [_article_json(r, read=read, saved=saved) for r in rows],
        "total": total,
        "personalized": bool(keywords),
        "logged_in": bool(uid),
        "read_filter": read_filter,
        "domain": domain,
        "query": query or "",
        "sort": sort,
    })


@app.route("/api/articles/<int:article_id>")
def api_article(article_id: int):
    conn = db.get_connection()
    db.init_db(conn)
    article = db.get_article(conn, article_id)
    if article is None:
        conn.close()
        return jsonify({"error": "not_found"}), 404
    dupes = db.get_duplicates(conn, article_id)

    uid = _uid()
    is_read = False
    saved = None
    saved_folder_name = None
    folders = []
    if uid:
        try:
            db.mark_read(conn, uid, article_id)
            is_read = True
        except Exception:  # ne jamais faire échouer la lecture d'un article
            conn.rollback()
        srow = db.get_saved(conn, uid, article_id)
        folders = [{"id": f["id"], "name": f["name"]} for f in db.list_folders(conn, uid)]
        if srow:
            saved = {"folder_id": srow["folder_id"]}
            if srow["folder_id"]:
                saved_folder_name = next(
                    (f["name"] for f in folders if f["id"] == srow["folder_id"]), None
                )
    conn.close()

    return jsonify({
        "article": _article_json(article, takeaways=True),
        "duplicates": [{"source": d["source"], "url": d["url"], "title": d["title"]}
                       for d in dupes],
        "crossed": len(dupes),
        "logged_in": bool(uid),
        "is_read": is_read,
        "saved": saved,
        "saved_folder_name": saved_folder_name,
        "folders": folders,
    })


@app.route("/api/articles/<int:article_id>/read", methods=["POST"])
@_api_login_required
def api_toggle_read(article_id: int):
    conn = db.get_connection()
    db.init_db(conn)
    read = _payload().get("read", True)
    if read is False or read == "false":
        db.mark_unread(conn, _uid(), article_id)
        state = False
    else:
        db.mark_read(conn, _uid(), article_id)
        state = True
    conn.close()
    return jsonify({"read": state})


@app.route("/api/articles/<int:article_id>/save", methods=["POST"])
@_api_login_required
def api_save(article_id: int):
    uid = _uid()
    data = _payload()
    folder_raw = data.get("folder_id")
    new_folder = (data.get("new_folder") or "").strip()
    conn = db.get_connection()
    db.init_db(conn)
    folder_id = None
    if new_folder:
        folder_id = db.create_folder(conn, uid, new_folder)
        if folder_id is None:
            match = next((f for f in db.list_folders(conn, uid)
                          if f["name"].lower() == new_folder.lower()), None)
            folder_id = match["id"] if match else None
    elif folder_raw not in (None, "", "null"):
        try:
            folder = db.get_folder(conn, uid, int(folder_raw))
            folder_id = folder["id"] if folder else None
        except (TypeError, ValueError):
            folder_id = None
    db.save_article(conn, uid, article_id, folder_id)
    conn.close()
    return jsonify({"saved": True, "folder_id": folder_id})


@app.route("/api/articles/<int:article_id>/unsave", methods=["POST"])
@_api_login_required
def api_unsave(article_id: int):
    conn = db.get_connection()
    db.init_db(conn)
    db.unsave_article(conn, _uid(), article_id)
    conn.close()
    return jsonify({"saved": False})


@app.route("/api/articles/refresh", methods=["POST"])
def api_articles_refresh():
    if not _ingest_state["running"]:
        conn = db.get_connection()
        db.init_db(conn)
        kwargs = _session_pipeline_kwargs(conn)  # BYOK : Claude / gratuit-Ollama selon le compte
        conn.close()
        _reset_ingest_state()
        _ingest_state["running"] = True
        _ingest_state["phase"] = "Démarrage…"
        threading.Thread(target=_run_ingest, args=(kwargs,), daemon=True).start()
    return jsonify({"started": True})


@app.route("/api/articles/refresh/status")
def api_articles_refresh_status():
    return jsonify({k: _ingest_state[k] for k in (
        "running", "done", "percent", "phase", "ingested", "summarized",
    )})


# --- Bibliothèque / dossiers ------------------------------------------------

@app.route("/api/library")
@_api_login_required
def api_library():
    conn = db.get_connection()
    db.init_db(conn)
    uid = _uid()
    folders = db.list_folders(conn, uid)
    counts = db.folder_counts(conn, uid)
    read = db.read_ids(conn, uid)
    saved = db.saved_ids(conn, uid)

    def pack(rows):
        return [_article_json(r, read=read, saved=saved) for r in rows]

    payload = {
        "folders": [
            {"id": f["id"], "name": f["name"],
             "count": counts.get(f["id"], 0),
             "articles": pack(db.list_saved(conn, uid, folder_id=f["id"]))}
            for f in folders
        ],
        "unfiled": pack(db.list_saved(conn, uid, folder_id=None)),
        "total": sum(counts.values()),
    }
    conn.close()
    return jsonify(payload)


@app.route("/api/folders", methods=["POST"])
@_api_login_required
def api_folder_create():
    name = (_payload().get("name") or "").strip()
    conn = db.get_connection()
    db.init_db(conn)
    fid = db.create_folder(conn, _uid(), name)
    conn.close()
    if fid is None:
        return jsonify({"error": "Nom de dossier vide ou déjà existant."}), 400
    return jsonify({"id": fid, "name": name})


@app.route("/api/folders/<int:folder_id>", methods=["DELETE", "POST"])
@_api_login_required
def api_folder_delete(folder_id: int):
    conn = db.get_connection()
    db.init_db(conn)
    db.delete_folder(conn, _uid(), folder_id)
    conn.close()
    return jsonify({"deleted": True})


# --- Tendances / digest / sources -------------------------------------------

@app.route("/api/trends")
def api_trends():
    conn = db.get_connection()
    db.init_db(conn)
    uid = _uid()
    read = db.read_ids(conn, uid) if uid else set()
    saved = db.saved_ids(conn, uid) if uid else set()
    data = trends.compute(conn)
    # Attache à chaque terme la liste de ses articles (mêmes objets que /api/articles :
    # résumé FR + lien interne + lu/enregistré) pour la pop-up du front.
    for bucket in ("trends", "weak"):
        for item in data.get(bucket, []):
            rows = db.get_by_ids(conn, item.get("article_ids") or [])
            item["articles"] = [_article_json(r, read=read, saved=saved) for r in rows]
    conn.close()
    return jsonify(data)


# Génération du digest hebdo en arrière-plan (une seule à la fois : appel LLM long).
_digest_gen = {"running": False, "done": False, "percent": 0, "phase": "", "week": "", "error": None}


def _reset_digest_gen() -> None:
    _digest_gen.update({"running": False, "done": False, "percent": 0, "phase": "",
                        "week": "", "error": None})


def _run_digest_gen(week_start=None, pipeline_kwargs=None) -> None:
    try:
        conn = db.get_connection()
        db.init_db(conn)
        row = weekly_digest.generate(conn, week_start, **(pipeline_kwargs or {}))
        conn.close()
        _digest_gen.update({"week": row["week_start"], "percent": 100, "phase": "Terminé"})
    except Exception as exc:
        _digest_gen.update({"percent": 100, "phase": f"Erreur : {exc}", "error": str(exc)})
    finally:
        _digest_gen["running"] = False
        _digest_gen["done"] = True


def _digest_json(row) -> dict:
    return {
        "week_start": row["week_start"],
        "week_end": row["week_end"],
        "content": row["content"],
        "article_count": row["article_count"],
        "model": row["model"],
        "generated_at": row["generated_at"],
    }


@app.route("/api/digest")
def api_digest():
    """Digests éditoriaux hebdomadaires archivés (dernier mois), du plus récent au plus ancien."""
    conn = db.get_connection()
    db.init_db(conn)
    rows = db.list_digests(conn, days=31)
    conn.close()
    start, end = weekly_digest.week_bounds()
    return jsonify({
        "digests": [_digest_json(r) for r in rows],
        "current_week": start,
        "current_week_end": end,
        "generating": _digest_gen["running"],
    })


@app.route("/api/digest/generate", methods=["POST"])
def api_digest_generate():
    """Rédige (en tâche de fond) le digest d'une semaine (défaut : la semaine courante)."""
    week = _payload().get("week_start") or None
    if not _digest_gen["running"]:
        conn = db.get_connection()
        db.init_db(conn)
        kwargs = _session_pipeline_kwargs(conn)  # BYOK : Claude (clé compte) / gratuit-Ollama
        conn.close()
        _reset_digest_gen()
        _digest_gen["running"] = True
        _digest_gen["phase"] = "Rédaction du digest…"
        threading.Thread(target=_run_digest_gen, args=(week, kwargs), daemon=True).start()
    return jsonify({"started": True})


@app.route("/api/digest/generate/status")
def api_digest_generate_status():
    return jsonify({k: _digest_gen[k] for k in (
        "running", "done", "percent", "phase", "week", "error",
    )})


@app.route("/api/sources")
def api_sources():
    conn = db.get_connection()
    db.init_db(conn)
    rows = db.list_sources(conn)
    conn.close()
    return jsonify({
        "sources": [_source_json(r) for r in rows],
        "discovery_enabled": discovery.enabled(),
        "refresh_running": _refresh_state["running"],
    })


@app.route("/api/sources/refresh", methods=["POST"])
def api_sources_refresh():
    if not discovery.enabled():
        return jsonify({"error": "discovery_disabled"}), 400
    if not _refresh_state["running"]:
        _reset_refresh_state()
        _refresh_state["running"] = True
        _refresh_state["phase"] = "Démarrage…"
        threading.Thread(target=_run_refresh, daemon=True).start()
    return jsonify({"started": True})


@app.route("/api/sources/refresh/status")
def api_sources_refresh_status():
    return jsonify({k: _refresh_state[k] for k in (
        "running", "done", "percent", "phase",
        "found", "validated", "kept", "added", "removed", "active",
    )})


# --- Réglages / compte ------------------------------------------------------

@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    conn = db.get_connection()
    db.init_db(conn)
    uid = _uid()

    allowed_models = {m["id"] for m in summarize.MODEL_CHOICES}

    if request.method == "POST":
        data = _payload()
        # Modèle Claude, appliqué au prochain « Chercher de nouveaux articles » sans
        # redéploiement. Per-compte si connecté (BYOK), sinon réglage global (invité).
        model = (data.get("model") or "").strip()
        if model in allowed_models:
            if uid:
                db.set_user_model(conn, uid, model)
            else:
                db.set_setting(conn, "anthropic_model", model)
        keywords = (data.get("keywords") or "").strip()
        if uid:
            hide_read = bool(data.get("hide_read"))
            db.set_preferences(conn, uid, keywords, hide_read)
        else:
            db.set_profile_keywords(conn, keywords)
        conn.close()
        return jsonify({"ok": True})

    if uid:
        pref = db.get_preferences(conn, uid)
        keywords = pref["keywords"] if pref and pref["keywords"] else ""
        hide_read = bool(pref["hide_read"]) if pref else False
    else:
        keywords = db.get_profile_keywords(conn)
        hide_read = False
    # Modèle affiché : celui du compte (BYOK) prime, sinon réglage global, sinon défaut.
    user_key = db.get_user_api_key(conn, uid) if uid else None
    model = (db.get_user_model(conn, uid) if uid else None) \
        or db.get_setting(conn, "anthropic_model") or summarize.current_model()
    # IA dispo si le compte connecté a sa clé (BYOK) OU si le serveur en a une (env).
    ia_enabled = bool(user_key or os.getenv("ANTHROPIC_API_KEY"))
    conn.close()
    return jsonify({
        "keywords": keywords,
        "hide_read": hide_read,
        "logged_in": bool(uid),
        "model": model,
        "models": summarize.MODEL_CHOICES,
        "ia_enabled": ia_enabled,
        "has_api_key": bool(user_key),
        "api_key_hint": _mask_key(user_key),
    })


@app.route("/api/account")
@_api_login_required
def api_account():
    conn = db.get_connection()
    db.init_db(conn)
    uid = _uid()
    user = db.get_user(conn, uid)
    stats = _account_stats(conn, uid)
    key = db.get_user_api_key(conn, uid)
    conn.close()
    return jsonify({
        "user": {"id": user["id"], "username": user["username"],
                 "created_at": user["created_at"]},
        "stats": stats,
        "has_api_key": bool(key),
        "api_key_hint": _mask_key(key),
    })


@app.route("/api/account/apikey", methods=["POST", "DELETE"])
@_api_login_required
def api_account_apikey():
    """BYOK : clé Claude perso du compte. Jamais renvoyée en clair (indice masqué)."""
    uid = _uid()
    conn = db.get_connection()
    db.init_db(conn)
    if request.method == "DELETE":
        db.set_user_api_key(conn, uid, None)
        conn.close()
        return jsonify({"ok": True, "has_api_key": False, "api_key_hint": None})
    key = (_payload().get("key") or "").strip()
    if not key:
        conn.close()
        return jsonify({"error": "Clé vide."}), 400
    if not key.startswith("sk-ant-"):
        conn.close()
        return jsonify({"error": "Format inattendu : une clé Anthropic commence par « sk-ant- »."}), 400
    db.set_user_api_key(conn, uid, key)
    hint = _mask_key(key)
    conn.close()
    return jsonify({"ok": True, "has_api_key": True, "api_key_hint": hint})


@app.route("/api/account/password", methods=["POST"])
@_api_login_required
def api_account_password():
    uid = _uid()
    data = _payload()
    current = data.get("current") or ""
    new = data.get("new") or ""
    confirm = data.get("confirm") or ""
    conn = db.get_connection()
    db.init_db(conn)
    user = db.get_user(conn, uid)
    error = None
    if not check_password_hash(user["password_hash"], current):
        error = "Mot de passe actuel incorrect."
    elif len(new) < 6:
        error = "Le nouveau mot de passe doit faire au moins 6 caractères."
    elif new != confirm:
        error = "Les deux nouveaux mots de passe ne correspondent pas."
    if error:
        conn.close()
        return jsonify({"error": error}), 400
    db.update_password(conn, uid, generate_password_hash(new))
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/account/delete", methods=["POST"])
@_api_login_required
def api_account_delete():
    conn = db.get_connection()
    db.init_db(conn)
    db.delete_user(conn, _uid())
    conn.close()
    session.clear()
    return jsonify({"deleted": True})


if __name__ == "__main__":
    # Debug désactivé par défaut (dev uniquement : FLASK_DEBUG=1).
    app.run(host="127.0.0.1", port=5000, debug=os.getenv("FLASK_DEBUG") == "1")
