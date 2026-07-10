# Le Guetteur — Front Next.js

Interface web de **Le Guetteur** (veille technologique auto-alimentée), réécrite en
**Next.js (App Router) + TypeScript + Tailwind + shadcn/ui**, rejouant les mêmes écrans
que le dashboard Flask/Jinja dans la charte **« Horizon clair »**.

Le front ne parle **jamais** à SQLite : il consomme l'**API JSON** exposée par le back Flask
(`/api/*`). La session (comptes, lu/non-lu, dossiers) passe par le **cookie Flask** — le front
proxifie `/api` vers le back, donc une seule origine côté navigateur, **pas de CORS**.

## Prérequis

- **Node.js ≥ 18.18** (20 LTS recommandé) + npm.
- Le **back** lancé en parallèle (voir `../back`), API sur `http://127.0.0.1:5000`.

## Démarrage

```bash
# 1) Back (dans un premier terminal, depuis RENDU/back)
uv run --no-sync python main.py serve       # API + dashboard Jinja sur :5000

# 2) Front (dans un second terminal, depuis RENDU/front)
npm install
npm run dev                                  # http://localhost:3000
```

> Astuce : `../start.sh` lance les deux en parallèle.

L'URL du back est surchargeable : `BACKEND_URL=http://127.0.0.1:5000 npm run dev`.

## Comment ça marche

- `next.config.mjs` réécrit `/api/:path*` → `${BACKEND_URL}/api/:path*`. Le navigateur ne
  voit que `localhost:3000` : le cookie de session Flask fonctionne sans configuration CORS.
- `lib/api.ts` : client typé (fetch `credentials: include`) de tous les endpoints.
- `components/session-provider.tsx` : contexte de session (interroge `/api/session`).
- Données chargées **côté client** (`use client` + `fetch`) — conforme au périmètre
  (« un simple fetch côté client suffit »), pas de SSR/ISR à gérer.
- Le **digest éditorial** est du Markdown rendu avec `react-markdown` + `remark-gfm`
  (styles `.markdown` dans `app/globals.css`).

## Écrans

| Route | Contenu |
|---|---|
| `/` | Articles : recherche, filtres (domaine, tri, lu/non-lu), bouton **Chercher de nouveaux articles** (barre de progression), enregistrer |
| `/article/[id]` | Résumé vulgarisé FR, points à retenir, sources croisées, lien officiel, enregistrer dans un dossier, marquer non lu |
| `/trends` | Tendances (jargon des domaines) + signaux faibles ; clic sur un terme → pop-up des articles liés |
| `/digest` | Digest éditorial hebdomadaire rédigé par le LLM (Markdown), historique par semaine + bouton « Générer » |
| `/sources` | Socle + sources découvertes (autorité, qualité, état) + **Rafraîchir** |
| `/library` | Articles enregistrés + dossiers thématiques (compte requis) |
| `/settings` | Mots-clés prioritaires + masquer les lus |
| `/account` | Infos, stats, mot de passe, suppression du compte |
| `/login`, `/register` | Comptes (sessions Flask) |

## Design system

`app/globals.css` porte les **tokens Horizon clair** en variables CSS ; `tailwind.config.ts`
les consomme. Les composants shadcn (`components/ui/*`) sont écrits sur ces tokens. On évite
les modificateurs d'opacité (`bg-primary/80`) sur les couleurs custom : teintes pleines
(`--primary-strong`) ou `color-mix()`.

## Périmètre (rappel)

Le dashboard **Jinja** du back reste fonctionnel en parallèle : couper Next et rouvrir
`http://127.0.0.1:5000` doit toujours marcher (l'API Flask ne dépend jamais du front).
