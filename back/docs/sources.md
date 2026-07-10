# Justification des sources

Cinq sources **socle** couvrant les quatre domaines, complétées par une **couche de
découverte autonome** (voir plus bas). Aucune ne requiert de clé payante ; le mode
dégradé reste pleinement fonctionnel sans clé API.

| Domaine | Source | Type | URL |
|---|---|---|---|
| Business de la tech | TechCrunch | RSS | `https://techcrunch.com/feed/` |
| Tech | Hacker News (Algolia) | API | `https://hn.algolia.com/api/v1/search?tags=story` |
| Data & IA | arXiv cs.AI | RSS | `https://rss.arxiv.org/rss/cs.AI` |
| UX & solutions numériques | Smashing Magazine | RSS | `https://www.smashingmagazine.com/feed/` |
| UX & solutions numériques | Nielsen Norman Group | RSS | `https://www.nngroup.com/feed/rss/` |

> Contrainte du sujet satisfaite : **RSS + au moins une API** (Hacker News Algolia).

---

## TechCrunch — Business de la tech
- **Autorité** : média de référence sur les startups, le financement et le business de la tech depuis 2005.
- **Indépendance** : rédaction éditoriale distincte de ses annonceurs ; large couverture multi-acteurs.
- **Angle** : levées de fonds, acquisitions, stratégie produit, mouvements du marché.
- **Limites** : biais vers l'écosystème US et les grosses opérations ; ton parfois promotionnel.

## Hacker News (API Algolia) — Tech
- **Autorité** : agrégateur communautaire (Y Combinator) ; le vote de la communauté fait remonter les signaux techniques forts.
- **Indépendance** : contenu soumis et trié par la communauté, pas par une rédaction.
- **Angle** : ingénierie, open source, sécurité, débats de fond ; utile pour détecter tôt une tendance.
- **Limites** : qualité hétérogène, titres parfois éditorialisés ; certains posts n'ont pas d'URL externe (lien HN utilisé en repli).

## arXiv cs.AI — Data & IA
- **Autorité** : dépôt de référence des preprints de recherche en IA.
- **Indépendance** : dépôt ouvert, non commercial.
- **Angle** : avancées scientifiques (modèles, méthodes, benchmarks) en amont de la vulgarisation.
- **Limites** : preprints non relus par les pairs ; titres et résumés très techniques.

## Smashing Magazine — UX & solutions numériques
- **Autorité** : référence historique du design web et front-end.
- **Indépendance** : ligne éditoriale propre, indépendante des plateformes.
- **Angle** : design d'interface, CSS/UX, accessibilité, bonnes pratiques concrètes.
- **Limites** : centré développement front-end ; moins de recherche UX fondamentale.

## Nielsen Norman Group — UX & solutions numériques
- **Autorité** : autorité mondiale de la recherche en utilisabilité (Jakob Nielsen, Don Norman).
- **Indépendance** : cabinet de recherche indépendant, méthodologie rigoureuse.
- **Angle** : recherche utilisateur, ergonomie, études d'usabilité fondées sur des données.
- **Limites** : rythme de publication faible ; contenu parfois adossé à leur offre de formation.

---

# Couche de découverte autonome (bonus)

Le socle ci-dessus reste **fixe et justifié**. Par-dessus, `Le Guetteur` peut **découvrir
seul** de nouvelles sources et **entretenir** l'ensemble. Commande dédiée, à la demande :
`python main.py discover` (activée par `SOURCE_DISCOVERY=1`). Les sources découvertes sont
stockées dans la table `sources` (`origin='discovered'`) et visibles sur la page **/sources**.

**Réalité technique** : un LLM local ne navigue pas. C'est le *code* qui découvre et **valide** ;
le LLM ne fait que **proposer** des médias, que le code vérifie avant tout ajout.

### Comment une source est trouvée (3 couches, toutes optionnelles, dégradé-safe)
1. **Autodécouverte de flux** (toujours active) : à partir d'un socle de sites curatés par domaine,
   on lit les balises `<link rel="alternate" type="application/rss+xml">` (ou les chemins `/feed`,
   `/rss`, `/atom.xml`…).
2. **Recherche web** (`DISCOVERY_WEB=1`, lib gratuite `ddgs`) : quelques requêtes par domaine → sites
   candidats → autodécouverte de leurs flux.
3. **Proposition par le LLM local** (`DISCOVERY_LLM=1`, Ollama) : le modèle liste des médias réputés
   (nom + URL) pour le domaine ; le code autodécouvre puis **valide** leurs flux.

### Comment une source est validée et notée
- Le flux doit **se parser** (feedparser) et présenter **≥ `DISCOVERY_MIN_RECENT` entrées récentes**
  (< `DISCOVERY_FRESH_DAYS`).
- **On-topic** : les titres récents doivent contenir des mots-clés du domaine (rejet sinon).
- **Dédoublonnage** vs les URLs déjà connues ; on garde le **top-N par domaine** (`DISCOVERY_MAX_PER_DOMAIN`).
- **Autorité initiale** = mélange fraîcheur + volume + on-topic (plafonnée, toujours < sources triées main).

### Comment l'ensemble s'auto-entretient (auto-élagage)
À chaque `python main.py`, une boucle **purement locale** note chaque source d'après la qualité réelle
de ses articles (volume, pertinence moyenne, taux de doublons) via une **moyenne mobile** `quality`,
puis :
- **élague** (désactive) les sources **découvertes** durablement faibles
  (`quality < SOURCE_QUALITY_MIN` après `SOURCE_MIN_RUNS` runs) ;
- **rapproche** leur autorité de la qualité observée (nourrit le score de pertinence).
Le **socle n'est jamais élagué** : le dashboard reste démontrable hors-ligne sur les 5 sources.
