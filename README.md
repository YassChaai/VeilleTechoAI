# Le Guetteur — Rendu

Plateforme de **veille technologique auto-alimentée** (Tech · Business de la tech · Data & IA · UX).
Elle ingère automatiquement de l'actualité, la **déduplique**, la **vulgarise en français**, la
**catégorise**, et l'affiche dans un **dashboard filtrable**. Tout le pipeline se relance en une
commande (`python main.py`).

Lien : https://le-guetteur-front.onrender.com/

## Structure du rendu

```
RENDU/
├── back/    → pipeline Python + API Flask (+ dashboard Jinja de secours)
│             main.py, ingestion/, processing/, storage/, dashboard/, data/, tests/
└── front/   → interface Next.js (App Router) + shadcn/ui, consomme l'API JSON du back
```

- **back/** = tout le métier : ingestion RSS/API, déduplication, résumé/vulgarisation (LLM
  local optionnel), score de pertinence, tendances, découverte de sources, comptes. Il expose
  à la fois le **dashboard Jinja** (`:5000`, autonome) et une **API JSON** (`/api/*`).
- **front/** = la **nouvelle interface** Next.js + Tailwind + shadcn (Phase 2). Elle proxifie
  `/api` vers le back : une seule origine, la session Flask (cookie) marche sans CORS.

> Le dashboard Jinja reste démontrable **seul** : couper Next et ouvrir `:5000` fonctionne
> toujours (l'API ne dépend jamais du front).

## Démarrage rapide

```bash
# Back — depuis RENDU/back
uv sync                                  # crée l'environnement (première fois)
uv run --no-sync python main.py          # lance le pipeline (ingestion → vulgarisation → stockage)
uv run --no-sync python main.py serve    # API + dashboard Jinja → http://127.0.0.1:5000

# Front — depuis RENDU/front (Node ≥ 18.18)
npm install
npm run dev                              # http://localhost:3000
```

Ou les deux d'un coup : `./start.sh` (à la racine de `RENDU/`).

## Déploiement en ligne

Blueprint Render prêt à l'emploi ([`render.yaml`](render.yaml)) : deux services web
(`le-guetteur-api` Python + `le-guetteur-front` Node) sur une seule plateforme. Le front
proxifie `/api` vers le back via `BACKEND_URL`. Guide pas-à-pas (blueprint **ou** création
manuelle, secrets, limites de l'offre gratuite) : [`DEPLOY.md`](DEPLOY.md).

Autres commandes back utiles : `main.py digest` (digests éditoriaux hebdo),
`main.py discover` (nouvelles sources), `main.py purge` (nettoyage), `main.py reset [all]`
(remise à zéro). Liste complète : [`back/README.md`](back/README.md).

## Points clés

- **Fonctionne sans clé** : avec **Ollama** (LLM local gratuit) le résumé est une vraie
  **vulgarisation FR** ; sans aucun LLM, repli extractif + catégorisation par mots-clés.
  Une clé `ANTHROPIC_API_KEY` bascule sur Claude sans changer de code.
- **Débit borné + base propre** : au plus 40 nouveaux articles par run (tous résumés dans le
  run), et purge des non-résumés en fin de run → jamais de « résumé en attente ».
- **Digest éditorial hebdomadaire** : synthèse rédigée par le LLM (TL;DR + sections par domaine),
  **archivée par semaine** (historique du dernier mois), page Digest + `main.py digest`.
- **Idempotent** : relancer `main.py` ne crée aucun doublon (`INSERT OR IGNORE` sur `url`).
- **Comptes** : inscription/connexion (sessions Flask, mots de passe hachés), préférences,
  suivi lu/non-lu, lecture-à-plus-tard avec dossiers. Navigation libre sans compte.
- Détails back : [`back/README.md`](back/README.md) · détails front : [`front/README.md`](front/README.md).
