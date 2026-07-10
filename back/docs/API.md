# API JSON — Le Guetteur (Phase 2)

L'API est exposée par `dashboard/app.py` sur le port **5000**, en parallèle du dashboard
Jinja. Elle est consommée par le front Next.js (`../front`), qui proxifie `/api` → Flask
(une seule origine, donc la **session Flask** — cookie — fonctionne sans CORS).

- **Base** : `http://127.0.0.1:5000/api`
- **Auth** : session par **cookie** (`Set-Cookie` à la connexion). Les routes marquées 🔒
  renvoient `401 {"error": "auth_required"}` si non connecté.
- **Corps** : JSON (repli accepté sur `form`). Réponses en JSON.
- **Erreurs** : code HTTP + `{"error": "..."}`.

## Méta & session

| Méthode | Route | Corps | Réponse |
|---|---|---|---|
| GET | `/api/meta` | — | `{app, domains[], discovery_enabled, semantic}` |
| GET | `/api/session` | — | `{user: {id, username} \| null}` |
| POST | `/api/register` | `{username, password, confirm}` | `{user}` ou `400 {error}` |
| POST | `/api/login` | `{username, password}` | `{user}` ou `401 {error}` |
| POST | `/api/logout` | — | `{ok: true}` |

## Articles

| Méthode | Route | Corps / Query | Réponse |
|---|---|---|---|
| GET | `/api/articles` | `?q&domain&sort=date\|relevance&read=all\|unread\|read` | `{articles[], total, personalized, logged_in, read_filter, domain, query, sort}` |
| GET | `/api/articles/{id}` | — | `{article, duplicates[], crossed, logged_in, is_read, saved, saved_folder_name, folders[]}` |
| POST 🔒 | `/api/articles/{id}/read` | `{read: bool}` | `{read}` |
| POST 🔒 | `/api/articles/{id}/save` | `{folder_id?, new_folder?}` | `{saved, folder_id}` |
| POST 🔒 | `/api/articles/{id}/unsave` | — | `{saved: false}` |
| POST | `/api/articles/refresh` | — | `{started}` — relance le pipeline en tâche de fond |
| GET | `/api/articles/refresh/status` | — | `{running, done, percent, phase, ingested, summarized}` |

Un objet **article** : `{id, source, url, title, title_original, category, domain_slug, summary,
excerpt, published_at, ingested_at, relevance, read?, saved?, takeaways?}`. `title` est le titre
**traduit en français** (repli sur `title_original` si non traduit).

## Bibliothèque & dossiers

| Méthode | Route | Corps | Réponse |
|---|---|---|---|
| GET 🔒 | `/api/library` | — | `{folders: [{id, name, count, articles[]}], unfiled[], total}` |
| POST 🔒 | `/api/folders` | `{name}` | `{id, name}` ou `400 {error}` |
| DELETE 🔒 | `/api/folders/{id}` | — | `{deleted: true}` (les articles repassent en « à lire ») |

## Tendances

| Méthode | Route | Réponse |
|---|---|---|
| GET | `/api/trends` | `{trends[], weak[], recent_days}` — items `{term, recent, baseline, lift, sources, score, example, articles[]}` (`articles` = objets article pour la pop-up) |

## Digest éditorial hebdomadaire

| Méthode | Route | Corps | Réponse |
|---|---|---|---|
| GET | `/api/digest` | — | `{digests[], current_week, current_week_end, generating}` |
| POST | `/api/digest/generate` | `{week_start?}` | `{started}` — rédige en tâche de fond (défaut : semaine courante) |
| GET | `/api/digest/generate/status` | — | `{running, done, percent, phase, week, error}` |

Un **digest** : `{week_start, week_end, content (Markdown), article_count, model, generated_at}`.

## Sources

| Méthode | Route | Réponse |
|---|---|---|
| GET | `/api/sources` | `{sources[], discovery_enabled, refresh_running}` |
| POST | `/api/sources/refresh` | `{started}` ou `400 {error: "discovery_disabled"}` |
| GET | `/api/sources/refresh/status` | `{running, done, percent, phase, found, validated, kept, added, removed, active}` |

Une **source** : `{id, name, type, url, domain, domain_slug, authority, origin (static\|discovered),
quality, active, runs, added_at, last_checked}`.

## Réglages & compte

| Méthode | Route | Corps | Réponse |
|---|---|---|---|
| GET | `/api/settings` | — | `{keywords, hide_read, logged_in}` |
| POST | `/api/settings` | `{keywords, hide_read}` | `{ok}` (par utilisateur si connecté, sinon profil invité) |
| GET 🔒 | `/api/account` | — | `{user: {id, username, created_at}, stats: {read, saved, folders}}` |
| POST 🔒 | `/api/account/password` | `{current, new, confirm}` | `{ok}` ou `400 {error}` |
| POST 🔒 | `/api/account/delete` | — | `{deleted}` (efface le compte et ses données) |

---

> Les routes **HTML Jinja** équivalentes (`/`, `/article/<id>`, `/digest`, `/sources`, `/library`,
> `/settings`, `/account`, `/login`, `/register`…) restent servies en parallèle : le dashboard
> Jinja est démontrable **seul**, sans le front Next (critère d'acceptation Phase 2).
