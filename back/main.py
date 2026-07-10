"""Point d'entrée unique du pipeline de veille.

Usage :
    python main.py          # pipeline complet : ingestion -> dedup -> résumé/catégo -> stockage
    python main.py serve    # lance le dashboard Flask (http://127.0.0.1:5000)
    python main.py embed    # bonus : calcule les embeddings manquants (recherche sémantique)
    python main.py discover # bonus : découvre de nouvelles sources (SOURCE_DISCOVERY=1)
    python main.py purge    # supprime les articles sans résumé (nettoyage du backlog)
    python main.py resummarize  # remet en attente les résumés anglais (re-vulgarisation FR)
    python main.py digest    # génère les digests éditoriaux hebdo du dernier mois
    python main.py reset [all] [-y]  # vide les articles (ou toute la base avec `all`)

Fonctionne de bout en bout SANS clé API (mode dégradé). Idempotent : relançable
sans créer de doublons.
"""

from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import yaml
from dotenv import load_dotenv

from ingestion import discovery, fetch_source
from processing import dedup, ranking, semantic_search, source_health, summarize, translate
from storage import db

load_dotenv()

SOURCES_FILE = "sources.yaml"


def _yaml_sources() -> list[dict]:
    """Le socle de sources déclaré dans sources.yaml (5 sources justifiées)."""
    with open(SOURCES_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f).get("sources", [])


def _sync_static_sources(conn) -> None:
    """Miroir du socle YAML dans la table `sources` (origin='static'), pour /sources
    et la boucle d'auto-ajustement. Idempotent (INSERT OR IGNORE sur url)."""
    for src in _yaml_sources():
        db.upsert_source(conn, {**src, "origin": "static"})


def load_sources(conn=None) -> list[dict]:
    """Sources à ingérer : socle YAML + découvertes actives (union). Sans conn → socle seul."""
    sources = _yaml_sources()
    if conn is not None:
        sources += [dict(r) for r in db.active_discovered_sources(conn)]
    return sources


def run_pipeline(on_progress=None, api_key=None, model=None,
                 translate_backend=None, require_llm=None) -> None:
    """Pipeline complet. `on_progress` : callback optionnel {phase, percent, ingested,
    summarized} pour alimenter une barre de progression (bouton « Chercher de nouveaux
    articles » du dashboard).

    Selon le compte déclencheur (BYOK) :
      - `api_key` / `model` : clé + modèle Claude (mode « Claude ») ;
      - `translate_backend` : force le backend de traduction (ex. 'auto' → tente Ollama
        pour le mode gratuit) ;
      - `require_llm` : False → autorise le repli extractif (anglais) ; True → pas d'anglais.
    None → valeurs d'environnement (utilisé au build sans utilisateur)."""

    def emit(phase: str, percent: float, **extra) -> None:
        if on_progress:
            on_progress({"phase": phase, "percent": int(percent), **extra})

    conn = db.get_connection()
    db.init_db(conn)
    _sync_static_sources(conn)

    # 1. Ingestion (idempotente : INSERT OR IGNORE sur url). Socle + découvertes actives.
    #    Plafond GLOBAL de nouveaux articles/run (MAX_NEW_PER_RUN), réparti en ROUND-ROBIN
    #    entre les sources → le plafond n'affame plus les dernières sources de la liste, et
    #    le résumé traite tous les nouveaux dans le même run (pas de backlog).
    emit("Ingestion des sources…", 2, ingested=0, summarized=0)
    limit = int(os.getenv("MAX_ITEMS_PER_SOURCE", "20"))
    max_new = int(os.getenv("MAX_NEW_PER_RUN", "40"))
    sources = load_sources(conn)

    # a) Récupère les items de chaque source (une file par source).
    queues: list[list] = []
    for i, source in enumerate(sources):
        try:
            items = fetch_source(source, limit)
        except Exception as exc:
            print(f"[ingest] ⚠️  {source.get('name')} : {exc}")
            continue
        queues.append([source["name"], iter(items)])
        emit(f"Ingestion · {source['name']}",
             2 + 18 * (i + 1) / max(len(sources), 1), ingested=0)

    # b) Insère en round-robin : 1 nouvel article par source et par tour, jusqu'au plafond.
    inserted = 0
    per_source: dict[str, int] = {name: 0 for name, _ in queues}
    while inserted < max_new and queues:
        progressed = False
        for entry in list(queues):
            if inserted >= max_new:
                break
            name, it = entry
            for item in it:                       # avance jusqu'au prochain NOUVEAU
                if db.insert_article(conn, item):
                    inserted += 1
                    per_source[name] += 1
                    progressed = True
                    break
            else:
                queues.remove(entry)              # source épuisée pour ce run
        if not progressed:
            break

    for name, n in per_source.items():
        print(f"[ingest] {name} : {n} nouveaux")
    emit("Ingestion terminée", 40, ingested=inserted)
    print(f"[ingest] → {inserted} nouveaux articles au total "
          f"(plafond {max_new}/run, round-robin entre sources)")

    # 2. Déduplication (marque duplicate_of_id, ne supprime rien).
    emit("Déduplication…", 42, ingested=inserted)
    marked = dedup.run_dedup(conn)
    print(f"[dedup]  → {marked} doublon(s) marqué(s)")

    # 3. Résumé + catégorisation des articles en attente (avancement en direct).
    #    Borné par run (idempotent : relancer traite le reste) et concurrent : les
    #    appels LLM sont lents mais bornés réseau/GPU. Les écritures SQLite restent
    #    sur le thread principal (connexion mono-thread) via as_completed.
    # Clé Claude : celle passée par l'appelant (BYOK, clé du compte qui déclenche le
    # refresh) prime ; None → retombe sur ANTHROPIC_API_KEY (env).
    summarize.set_api_key(api_key)
    summarize.set_require_llm(require_llm)
    translate.set_backend_override(translate_backend)
    ia = summarize.ia_enabled()
    # Modèle : celui du compte (BYOK) prime, sinon réglage global, sinon ANTHROPIC_MODEL/défaut.
    if ia:
        summarize.set_model(model or db.get_setting(conn, "anthropic_model"))
    # Garde-fou coût : on plafonne seulement en mode IA (Claude, payant). En mode
    # dégradé (LLM local gratuit), on traite TOUT le backlog en attente.
    if ia:
        pending = db.articles_without_summary(conn, int(os.getenv("MAX_ENRICH_PER_RUN", "40")))
    else:
        pending = db.articles_without_summary(conn, 1_000_000)
    total = len(pending)

    mode = "IA (Claude)" if ia else "dégradé (mots-clés)"
    if not ia and translate.available():
        fr = "vulgarisation FR" if translate.has_generative_llm() else "traduction FR"
        mode += f" + {fr} ({translate.backend()})"

    if total:
        workers = max(1, int(os.getenv("ENRICH_WORKERS", "3")))
        print(f"[résumé] {total} article(s) à traiter — mode {mode} — {workers} worker(s)",
              flush=True)
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(summarize.summarize_and_categorize, dict(art)): art
                for art in pending
            }
            for fut in as_completed(futures):
                art = futures[fut]
                done += 1
                try:
                    res = fut.result()
                except Exception as exc:  # article laissé en attente pour le prochain run
                    print(f"[résumé]   {done}/{total}  ✗  {art['title'][:45]} ({exc})",
                          flush=True)
                    continue
                if res is None:  # REQUIRE_LLM_SUMMARY=1 + LLM indispo → on n'écrit PAS d'anglais
                    print(f"[résumé]   {done}/{total}  ⏭  {art['title'][:45]} "
                          "(LLM indispo — laissé en attente)", flush=True)
                    continue
                db.update_enrichment(
                    conn, art["id"], res["summary"], res["category"], res["takeaways"]
                )
                # Mode IA (Claude) : le titre FR est produit dans le même appel → on le
                # stocke ici. En mode dégradé (pas de title_fr), la phase 3c s'en charge.
                if res.get("title_fr"):
                    db.update_title_fr(conn, art["id"], res["title_fr"])
                print(f"[résumé]   {done}/{total}  ✓  {art['title'][:55]}", flush=True)
                emit(f"Résumé {done}/{total}", 45 + 45 * done / total,
                     ingested=inserted, summarized=done)
        print(f"[résumé] → {total} article(s) traité(s) — mode {mode}", flush=True)
    else:
        emit("Aucun nouvel article à résumer", 90, ingested=inserted, summarized=0)

    # 3b. Purge : la base ne garde QUE des articles résumés. On supprime ceux restés
    #     sans résumé (échecs LLM ponctuels) — ils seront réingérés/retentés au run suivant.
    emit("Nettoyage…", 91, ingested=inserted, summarized=total)
    purged = db.purge_unsummarized(conn)
    if purged:
        print(f"[purge]  → {purged} article(s) sans résumé supprimé(s)")

    # 3c. Traduction FR des titres manquants (pour l'affichage). Concurrent, court.
    #     Repli silencieux sur le titre original si aucun backend (title_fr laissé NULL).
    if translate.available():
        titles = db.articles_without_title_fr(conn, 100000)
        if titles:
            emit("Traduction des titres…", 92, ingested=inserted, summarized=total)
            tworkers = max(1, int(os.getenv("ENRICH_WORKERS", "3")))
            done_t = 0
            with ThreadPoolExecutor(max_workers=tworkers) as pool:
                tfut = {pool.submit(translate.translate_title, r["title"]): r for r in titles}
                for fut in as_completed(tfut):
                    r = tfut[fut]
                    try:
                        fr = (fut.result() or "").strip()
                    except Exception:
                        continue
                    if fr:
                        db.update_title_fr(conn, r["id"], fr)
                        done_t += 1
            print(f"[titres] → {done_t}/{len(titles)} titre(s) traduit(s) en FR")

    # 4. Bonus : score de pertinence enrichi (autorité + fraîcheur + sources croisées).
    emit("Score de pertinence…", 93, ingested=inserted, summarized=total)
    ranked = ranking.compute_relevance(conn)
    print(f"[score]  → pertinence calculée pour {ranked} article(s)")

    # 5. Bonus : auto-ajustement des sources (dédup + qualité observée → élagage des faibles).
    emit("Mise à jour des sources…", 96, ingested=inserted, summarized=total)
    evaluated, pruned, deduped = source_health.run(conn)
    active = len(db.active_discovered_sources(conn))
    print(f"[sources] {evaluated} évaluée(s), {pruned} élaguée(s), {deduped} doublon(s) retiré(s) "
          f"— {active} découverte(s) active(s)")

    # 6. Bonus : embeddings si la recherche sémantique est activée.
    if semantic_search.available():
        emit("Embeddings…", 98, ingested=inserted, summarized=total)
        embed_missing(conn)

    print(f"[ok]     base : {db.count_articles(conn)} articles")
    emit("Terminé", 100, ingested=inserted, summarized=total)
    conn.close()


def discover() -> None:
    """Bonus : découvre, valide et ajoute de nouvelles sources (SOURCE_DISCOVERY=1)."""
    conn = db.get_connection()
    db.init_db(conn)
    _sync_static_sources(conn)
    if not discovery.enabled():
        print("[discover] désactivé — export SOURCE_DISCOVERY=1 (+ DISCOVERY_WEB / DISCOVERY_LLM)")
        conn.close()
        return
    existing = db.existing_source_urls(conn)
    candidates = discovery.discover(existing)
    added = sum(db.upsert_source(conn, c) for c in candidates)
    removed = source_health.dedupe_sources(conn)  # filet de sécurité anti-doublons
    print(f"[discover] → {added} source(s) ajoutée(s) sur "
          f"{len(candidates)} candidat(s) validé(s)"
          + (f", {removed} doublon(s) retiré(s)" if removed else ""))
    conn.close()


def embed_missing(conn=None) -> None:
    """Calcule les embeddings manquants (bonus recherche sémantique)."""
    own = conn is None
    if own:
        conn = db.get_connection()
        db.init_db(conn)
    if not semantic_search.available():
        print("[embed] recherche sémantique désactivée "
              "(export SEMANTIC_SEARCH=1 + pip install sentence-transformers)")
        if own:
            conn.close()
        return
    rows = db.articles_without_embedding(conn)
    for row in rows:
        blob = semantic_search.embed_text(f"{row['title']} {row['content'] or ''}")
        db.set_embedding(conn, row["id"], blob)
    print(f"[embed]  → {len(rows)} embedding(s) calculé(s)")
    if own:
        conn.close()


def purge() -> None:
    """Supprime tous les articles sans résumé (nettoyage du backlog)."""
    conn = db.get_connection()
    db.init_db(conn)
    removed = db.purge_unsummarized(conn)
    print(f"[purge]  → {removed} article(s) sans résumé supprimé(s) — "
          f"reste {db.count_articles(conn)} article(s) résumé(s)")
    conn.close()


def resummarize() -> None:
    """Remet en attente les résumés non français (repli extractif anglais) pour
    qu'ils soient re-vulgarisés en FR au prochain run (Ollama requis)."""
    conn = db.get_connection()
    db.init_db(conn)
    n = db.reset_untranslated_summaries(conn)
    conn.close()
    print(f"[resummarize] → {n} résumé(s) non français remis en attente. "
          "Relance `python main.py` (Ollama démarré) pour les re-vulgariser.")


def digest_cmd() -> None:
    """Génère (ou régénère) les digests hebdomadaires du dernier mois."""
    from processing import digest as weekly_digest

    conn = db.get_connection()
    db.init_db(conn)
    results = weekly_digest.backfill(conn, weeks=4)
    for row in results:
        print(f"[digest] semaine {row['week_start']} → {row['article_count']} article(s) "
              f"— modèle {row['model']}")
    if not results:
        print("[digest] aucune semaine avec des articles à couvrir")
    conn.close()


def reset() -> None:
    """Remet la base à zéro. `reset` = articles seuls ; `reset all` = tout (comptes,
    sources, digests…). Options : -y / --yes pour sauter la confirmation."""
    args = sys.argv[2:]
    full = "all" in args or "--all" in args
    assume_yes = "-y" in args or "--yes" in args

    conn = db.get_connection()
    db.init_db(conn)
    n = db.count_articles(conn)
    scope = ("TOUTE la base (articles, comptes, dossiers, préférences, sources, digests)"
             if full else f"les {n} article(s) + lectures, enregistrements et digests "
                          "(comptes et sources conservés)")
    print(f"⚠️  Reset : suppression définitive de {scope}.")
    if not assume_yes:
        try:
            answer = input("Confirmer ? tape 'oui' : ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("oui", "o", "yes", "y"):
            print("Annulé.")
            conn.close()
            return
    removed = db.reset_articles(conn, full=full)
    conn.close()
    print(f"[reset] → {removed} article(s) supprimé(s). "
          "Relance `python main.py` pour ré-ingérer (Ollama démarré pour le FR).")


def serve() -> None:
    from dashboard.app import app

    app.run(host="127.0.0.1", port=5000, debug=False)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "serve":
        serve()
    elif cmd == "embed":
        embed_missing()
    elif cmd == "discover":
        discover()
    elif cmd == "purge":
        purge()
    elif cmd == "resummarize":
        resummarize()
    elif cmd == "digest":
        digest_cmd()
    elif cmd == "reset":
        reset()
    else:
        run_pipeline()


if __name__ == "__main__":
    main()
