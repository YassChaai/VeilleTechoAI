# 🛰️ Le Guetteur — plateforme de veille technologique auto-alimentée

> **Le Guetteur** surveille l'actualité tech (Tech · Business de la tech · Data & IA · UX)
> et t'en livre l'essentiel, vulgarisé en français.

Agrège automatiquement l'actualité **Tech · Business de la tech · Data & IA · UX**
depuis 5 sources fiables, la **déduplique**, la **résume**, la **catégorise**, et
l'affiche dans un **dashboard filtrable**. Tout le pipeline se relance en **une seule
commande** — la preuve d'auto-alimentation, démontrée en direct en soutenance.

## Démarrage rapide

Avec [uv](https://docs.astral.sh/uv/) (recommandé — projet géré par `pyproject.toml` + `uv.lock`, Python 3.11 automatique) :

```bash
# 1. Environnement (crée .venv en Python 3.11 et installe depuis uv.lock)
uv sync

# 2. (optionnel) mode IA
cp .env.example .env        # puis renseigner ANTHROPIC_API_KEY si souhaité

# 3. Alimenter la base (ingestion → dédup → résumé → stockage)
uv run python main.py

# 4. Ouvrir le dashboard
uv run python main.py serve # http://127.0.0.1:5000
```

<details>
<summary>Sans uv (venv standard, Python 3.11+)</summary>

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py
python main.py serve
```
</details>

> **Sans clé API**, tout fonctionne : avec **Ollama** (LLM local gratuit) le résumé est
> une **vulgarisation en français** ; sans aucun LLM, repli sur un résumé extractif +
> catégorisation par mots-clés. Ajouter `ANTHROPIC_API_KEY` au `.env` bascule
> automatiquement en **mode IA** (Claude), **sans modifier le code**.

## Fonctionnement

Pipeline en 4 couches, orchestré par [`main.py`](main.py) :

```
sources.yaml → ingestion/ → processing/ → storage/ → dashboard/
               (RSS + API)  (dédup +       (SQLite)   (Flask +
                            résumé/catégo)             Jinja2)
```

- **Ingestion** — connecteur RSS générique + connecteur API Hacker News, pilotés
  par `sources.yaml`. Idempotent (`INSERT OR IGNORE` sur `url`).
- **Déduplication** — 2 niveaux : hash du titre normalisé, puis similarité floue
  (`difflib` > 0.85) sur 48h. Les doublons sont **marqués** (`duplicate_of_id`),
  jamais supprimés.
- **Résumé / catégorisation** — mode dégradé par défaut, mode IA (Claude) si clé.
- **Dashboard** — liste triée, filtre par domaine, recherche texte. Un clic sur un article
  ouvre une **page de synthèse** (`/article/<id>`) : résumé + **points à retenir**, plus un
  lien vers l'article officiel pour approfondir.
- **Comptes & personnalisation** — inscription/connexion (sessions Flask, mots de passe hachés).
  Connecté, chaque utilisateur a ses **préférences**, un suivi **lu/non-lu** (les lus ne sont pas
  mis en avant, filtre Tous/Non lus/Lus) et une **bibliothèque** « à lire plus tard » organisée en
  **dossiers thématiques**. La navigation reste **libre sans compte**.

> **Résumés en français** :
> - **Mode IA** (clé `ANTHROPIC_API_KEY`) : résumé et points à retenir rédigés directement en français par Claude.
> - **Mode dégradé + Ollama** (LLM local génératif) : le modèle **lit l'article complet** et rédige une
>   **vulgarisation en français** (résumé accessible + points à retenir), compréhensible sans connaître le
>   sujet — ce n'est pas une simple traduction. Installer **Ollama** puis `ollama pull llama3.2:3b`.
> - **Mode dégradé + Argos** (traducteur hors-ligne, `pip install argostranslate`) : résumé extractif
>   **traduit** en français, à défaut de backend génératif.
> - Config dans `.env` (`TRANSLATE_BACKEND=auto`). Sans backend, le résumé extractif reste dans la langue d'origine.
> - **`REQUIRE_LLM_SUMMARY=1`** : si le LLM est injoignable au moment du résumé, l'article est **laissé
>   en attente** (retenté au run suivant) plutôt que de produire un repli extractif anglais — garantit
>   qu'aucun résumé anglais ne persiste.

> **Titres traduits** : le titre de chaque article est traduit en français (colonne `title_fr`,
> affiché partout ; le titre original reste visible sur la page détail). La traduction **préserve les
> noms propres** (entreprises, produits, marques : Anthropic, Claude, OpenAI…) et **saute les titres
> déjà en français** (pas de re-traduction). Repli silencieux sur le titre original si le LLM est indispo.

> **Qualité de l'ingestion** : un filtre écarte les entrées sans corps exploitable (liens sans texte,
> « contenu » réduit au titre) — `MIN_CONTENT_CHARS`. Option `ENRICH_FULLTEXT=1` (nécessite
> `uv add trafilatura`) : va chercher le **texte intégral** des pages pour que la vulgarisation
> parte de l'article entier — cela réhabilite notamment Hacker News (liens nus) et TechCrunch (chapô).

## Commandes

| Commande | Effet |
|---|---|
| `python main.py` | Pipeline complet (ingestion → dédup → résumé → purge → stockage) |
| `python main.py serve` | Lance le dashboard Flask **+ l'API JSON** sur le port 5000 |
| `python main.py embed` | Bonus : calcule les embeddings (recherche sémantique) |
| `python main.py discover` | Bonus : découvre et valide de nouvelles sources (`SOURCE_DISCOVERY=1`) |
| `python main.py digest` | Bonus : rédige les digests éditoriaux hebdo du dernier mois |
| `python main.py purge` | Supprime les articles sans résumé (nettoyage du backlog) |
| `python main.py resummarize` | Remet en attente les résumés non-FR pour re-vulgarisation |
| `python main.py reset [all]` | Remet la base à zéro (articles seuls, ou tout avec `all`) — confirmation |

Relancer `python main.py` plusieurs fois **ne crée aucun doublon**.

> **Débit borné, base toujours « propre »** : chaque run ingère au plus
> `MAX_NEW_PER_RUN` (40) **nouveaux** articles — le résumé les traite donc tous dans
> le même run. En fin de run, une **purge** supprime les articles restés sans résumé
> (échecs LLM ponctuels) : la base ne contient que des articles résumés, donc aucun
> « résumé en attente » côté dashboard. Idempotent et self-healing (les purgés sont
> réingérés/retentés au run suivant).

## Auto-alimentation

- **Minimum** : `python main.py` récupère et met à jour les données en une commande.
- **Visé** : [`.github/workflows/pipeline.yml`](.github/workflows/pipeline.yml)
  relance le pipeline toutes les 6h via GitHub Actions.

## Front Next.js & API JSON (Phase 2)

`dashboard/app.py` sert **deux interfaces en parallèle** sur le port 5000 :

- le **dashboard Jinja** (HTML rendu côté serveur, **autonome** — démontrable seul) ;
- une **API JSON** sous `/api/*` (articles, auth, lu/non-lu, dossiers, tendances, digest,
  sources, compte…) — voir la référence [`docs/API.md`](docs/API.md).

Le **front Next.js** (App Router + shadcn/ui) vit dans [`../front`](../front) et consomme
cette API (il proxifie `/api` vers Flask → une seule origine, session cookie sans CORS).
**Critère d'acceptation Phase 2 respecté** : couper Next et rouvrir `:5000` fonctionne
toujours — l'API Flask ne dépend jamais du front. Détails : [`../front/README.md`](../front/README.md).

## Bonus (les 6 paliers du sujet)

- **Recherche sémantique** — `sentence-transformers` (`all-MiniLM-L6-v2`, local, sans clé).
  Activer : décommenter la dépendance, `export SEMANTIC_SEARCH=1`, puis `python main.py embed`.
- **Digest éditorial hebdomadaire** — un **digest rédigé** (TL;DR + une section par domaine +
  signal faible + à suivre, en Markdown) généré par le LLM à partir des articles de la semaine,
  **archivé par semaine** (table `digests`, historique du dernier mois). Les liens pointent vers
  **nos pages internes** `/article/<id>` (pas les sources), et une section finale déterministe
  **« Articles de la semaine »** garantit des liens cliquables même si le LLM les omet.
  `python main.py digest` (ou le bouton « Générer » du front) ; API `/api/digest`. Dégradé-safe :
  Claude si clé → Ollama sinon → digest assemblé factuellement si aucun LLM.
- **Détection de tendances / signaux faibles** — route `/trends` : termes qui montent
  (corroborés par ≥ 2 sources) vs baseline, + signaux émergents. **Seul le jargon des domaines
  remonte** : on ne garde que les termes d'un **lexique tech/métier** ou de forme technique
  (acronymes `GPU`/`LLM`, CamelCase `OpenAI`, versionnés `gpt4`) — pas les verbes/adjectifs. Sur le
  front, un clic sur un terme ouvre la **liste de nos articles liés** (résumé FR + lien interne).
- **Personnalisation** — route `/settings` (mots-clés pondérés, réordonne la liste).
- **Score de pertinence enrichi** — `relevance` = **0.55·autorité + 0.30·fraîcheur + 0.15·sources croisées**.
  Tri « Pertinence » sur le dashboard (`?sort=relevance`).
- **Déploiement en ligne** — `Dockerfile`, `Procfile`, `render.yaml` fournis (voir ci-dessous).
- **Sources dynamiques & autonomes** — au-delà des 5 sources socle, `python main.py discover`
  découvre de nouvelles sources (autodécouverte de flux + recherche web `ddgs` + proposition du LLM
  local, **validées** avant ajout). Une boucle d'auto-ajustement note chaque source et **élague** les
  découvertes faibles (jamais le socle). Visible sur la page **/sources**. Détails :
  [`docs/sources.md`](docs/sources.md).

## Déploiement en ligne (plateforme « toujours active »)

```bash
# Docker (local ou n'importe quel hébergeur conteneurs)
docker build -t veille-tech .
docker run -p 8000:8000 veille-tech        # http://localhost:8000
```

- **Render** : `render.yaml` déclare un service web (`gunicorn`) qui s'auto-alimente au démarrage.
- **Railway / Heroku** : `Procfile` (`release: python main.py`, `web: gunicorn …`).
- Ajouter `ANTHROPIC_API_KEY` en variable d'environnement pour le mode IA.

> **⚠️ Persistance** : SQLite doit vivre sur un **disque persistant** (`VEILLE_DB`), sinon la base est
> perdue à chaque redeploy. Sur Render, un cron est un service **séparé** qui ne partage pas le disque
> du web ; pour un rafraîchissement périodique portable, on privilégie **GitHub Actions**
> ([`.github/workflows/pipeline.yml`](.github/workflows/pipeline.yml)). Un vrai partage cron↔web
> nécessite un datastore commun (ex. Postgres managé).

## Structure

```
main.py                 # point d'entrée (run · serve · embed · discover · digest · purge · resummarize · reset)
sources.yaml            # config des 5 sources (+ autorité)
ingestion/              # rss.py · api_sources.py · discovery.py · fulltext.py
processing/             # dedup · summarize · ranking · trends · semantic_search · translate · source_health · digest
storage/                # db.py · schema.sql (articles, users, préférences, dossiers, sources, digests…)
dashboard/              # app.py (HTML Jinja + API JSON /api/*) · templates/ · static/
docs/                   # sources.md (justif. sources) · API.md (référence API JSON)
.github/workflows/      # cron d'auto-alimentation
data/veille.db          # base SQLite (générée)
```

> Le **front Next.js** est un projet séparé dans [`../front`](../front).

## Documentation

- [`docs/API.md`](docs/API.md) — référence de l'API JSON (`/api/*`) consommée par le front Next.
- [`docs/sources.md`](docs/sources.md) — justification des sources (autorité, indépendance, angle, limites).
- [`../DOCS/Project Brainstorming Claude.md`](../DOCS/Project%20Brainstorming%20Claude.md) — spec de référence (racine du dépôt).
- [`../CLAUDE.md`](../CLAUDE.md) — règles de travail et contraintes du projet (racine du dépôt).
