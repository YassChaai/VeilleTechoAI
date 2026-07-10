# Déploiement — Le Guetteur (tout sur Render)

Deux services web sur Render, une seule plateforme :

| Service | Rôle | Runtime | Dossier |
|---|---|---|---|
| `le-guetteur-api` | Pipeline + Flask (dashboard Jinja **et** API JSON `/api/*`) | Python | `back/` |
| `le-guetteur-front` | Interface Next.js, proxifie `/api` vers le back | Node | `front/` |

Le navigateur ne parle qu'au **front** ; Next reproxifie `/api/*` vers le back via
`BACKEND_URL` → **une seule origine**, le cookie de session Flask marche sans CORS.

---

## Prérequis : pousser le code sur Git

Render déploie depuis un dépôt GitHub/GitLab. La **racine du dépôt doit être `RENDU/`**
(elle contient `back/`, `front/` et `render.yaml`). Depuis `RENDU/` :

```bash
git init
git add .
git commit -m "Le Guetteur — déploiement Render"
git branch -M main
git remote add origin git@github.com:<toi>/le-guetteur.git
git push -u origin main
```

> Si tu préfères pousser tout `MINI-PROJET/`, déplace `render.yaml` à la racine du dépôt
> et préfixe les `rootDir` par `RENDU/` (`rootDir: RENDU/back`, `rootDir: RENDU/front`).

`data/veille.db`, `.env`, `node_modules/`, `.next/` sont déjà ignorés — la base est
**reconstruite au build** (voir plus bas), rien de lourd ni de secret n'est poussé.

---

## Option A — Blueprint (recommandé, tout en un clic)

Le fichier [`render.yaml`](render.yaml) décrit déjà les deux services.

1. Render → **New +** → **Blueprint**.
2. Connecte le dépôt → Render lit `render.yaml` → **Apply**.
3. Renseigne le secret demandé :
   - **`ANTHROPIC_API_KEY`** (facultatif) sur `le-guetteur-api` → résumés, catégories et
     français par Claude. Sans clé, le pipeline tourne quand même (résumés extractifs).
4. Premier déploiement fait, **récupère l'URL publique du back** (`le-guetteur-api…onrender.com`)
   et vérifie que **`BACKEND_URL`** du front la vise exactement (Render peut ajouter un suffixe
   si le nom est pris). Corrige la variable côté `le-guetteur-front` si besoin → **Manual Deploy**.
5. Ouvre l'URL du front : c'est le site complet. L'URL du back sert le **dashboard Jinja**
   autonome (`/`) — utile en soutenance pour prouver que le back tient sans le front.

---

## Option B — À la main (deux services, sans blueprint)

### 1. Back — `le-guetteur-api`
Render → New + → **Web Service** → dépôt → :
- **Root Directory** : `back`
- **Runtime** : Python 3 · **Build** : `pip install -r requirements.txt && python main.py`
- **Start** : `gunicorn dashboard.app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
- **Env** : `PYTHON_VERSION=3.11.9`, `VEILLE_DB=data/veille.db`, `SECRET_KEY=<aléatoire>`,
  `TRANSLATE_BACKEND=off`, `REQUIRE_LLM_SUMMARY=0`, `ANTHROPIC_MODEL=claude-opus-4-8`,
  et éventuellement `ANTHROPIC_API_KEY=<secret>`.

### 2. Front — `le-guetteur-front`
Render → New + → **Web Service** → même dépôt → :
- **Root Directory** : `front`
- **Runtime** : Node · **Build** : `npm ci --include=dev && npm run build` · **Start** : `npm run start`
- **Env** : `NODE_VERSION=20.11.1`, `BACKEND_URL=https://le-guetteur-api.onrender.com`
  (l'URL réelle du service back de l'étape 1).

---

## Ce qui a été adapté pour le cloud

- **`front/package.json`** : `start` = `next start -H 0.0.0.0` → écoute le `$PORT` imposé par
  Render (et reste sur 3000 en local).
- **Ingestion au build** (`… && python main.py`) : la base est peuplée dans le filesystem servi,
  donc gunicorn se lie au port tout de suite (pas de cold-start qui dépasse le health check).
- **1 worker gunicorn + threads** : les jobs de fond (refresh sources, digest) gardent leur état
  en mémoire du process ; plusieurs workers casseraient le polling de progression.
- **`TRANSLATE_BACKEND=off`** : aucun Ollama en prod → on n'essaie pas de le joindre.

## Limites à connaître (offre gratuite)

- **Base SQLite éphémère.** Reconstruite **à chaque redeploy** (vrais articles frais), mais les
  **comptes / lu-non-lu / bibliothèque** sont réinitialisés entre deux déploiements. Pour les
  conserver : ajoute un **disque persistant** (offre payante) monté p.ex. sur `/var/data` et mets
  `VEILLE_DB=/var/data/veille.db`.
- **Mise en veille.** Un service web gratuit s'endort après ~15 min d'inactivité → premier appel
  ensuite lent (~50 s), le temps du réveil. Sans conséquence sur les données.
- **Auto-alimentation.** Chaque redeploy relance le pipeline au build. Pour un rafraîchissement
  périodique : crée un **Deploy Hook** sur `le-guetteur-api` et déclenche-le en cron (GitHub
  Actions, cron-job.org…). Le workflow [`back/.github/workflows/pipeline.yml`](back/.github/workflows/pipeline.yml)
  peut servir de base.

## Vérification post-déploiement

1. `https://le-guetteur-api.onrender.com/` → dashboard Jinja avec de vrais articles.
2. `https://le-guetteur-api.onrender.com/api/articles` → JSON non vide.
3. `https://le-guetteur-front.onrender.com/` → interface Next ; Articles/Tendances/Digest/Sources
   chargent (donc le proxy `/api` → back fonctionne).
4. Inscription puis connexion sur le front → un compte se crée (cookie de session OK à travers
   le proxy). Il disparaîtra au prochain redeploy si aucun disque persistant n'est monté.
