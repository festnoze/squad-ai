# Gagner un edge sur Polymarket avec des agents IA automatisés (newsfeed + analyse)

> Document de recherche & de raisonnement itératif ("loop thinking").
> Statut : DRAFT — sections recherche en cours de consolidation (deep-research multi-sources).
> Date : 2026-06-10

---

## 0. Cadrage

**Question** : comment des agents IA automatisés, branchés sur des flux d'actualité
et des pipelines d'analyse, peuvent-ils obtenir un avantage (arbitrage au sens
strict, ou edge probabiliste) sur Polymarket ?

**Périmètre** :
1. Mécanique de marché Polymarket pertinente pour l'edge (CLOB, frais, oracle UMA, neg-risk)
2. Classes d'arbitrage documentées
3. Edge de latence sur les news
4. Architectures d'agents IA
5. Économie réaliste (spreads, frais, capital, concurrence)
6. Risques et contraintes (ToS, géo, oracle, régulation)

---

## 1. Loop thinking — itérations de raisonnement

(Premiers principes ; les faits vérifiés sont en section 2+.)

### Itération 1 — « l'arbitrage évident existe-t-il encore ? »

Hypothèse naïve : acheter YES + NO < 1$ sur le même marché, profit sans risque.

Raisonnement : si ce free lunch existait durablement, des bots triviaux le
mangeraient. Sur un CLOB liquide, l'écart YES+NO ≠ 1 ne survit que :
- sur les marchés **illiquides** (longue traîne), où la taille capturable est minuscule ;
- pendant des **fenêtres de volatilité** (breaking news) où les market makers
  retirent leurs quotes ;
- sur les structures **multi-outcomes** (somme des YES ≠ 1 sur N candidats),
  plus dures à surveiller — c'est combinatoire, donc moins de concurrents.

→ Conclusion provisoire : l'arb pur existe mais est un jeu d'infrastructure
(vitesse, couverture exhaustive des marchés), pas un jeu d'intelligence.
L'IA n'y apporte presque rien ; un scanner déterministe suffit.

### Itération 2 — « où l'IA apporte-t-elle un edge que la vitesse seule n'apporte pas ? »

Reformulation : l'edge durable = être **mieux calibré** que le marché sur la
probabilité réelle, pas seulement plus rapide.

Trois familles où un LLM/agent a un avantage structurel :
- **Lecture sémantique de la résolution** : les marchés Polymarket se résolvent
  sur des critères textuels précis (règles UMA). Beaucoup de traders parient le
  *titre* du marché, pas sa *règle de résolution*. Un agent qui parse la règle,
  identifie les cas limites (« avant le 30 juin », « selon source X »...) et
  price l'écart titre/règle a un edge réel et peu concurrentiel.
- **Fusion d'information multi-sources** : croiser sondages + données officielles
  + presse locale + réseaux sociaux plus vite et plus largement qu'un humain.
- **Couverture de la longue traîne** : des centaines de marchés à faible volume
  qu'aucun humain sérieux ne suit ; un agent peut tous les pricer en continu.

→ L'IA est un multiplicateur de **largeur** (nombre de marchés couverts) et de
**profondeur de lecture** (règles, contexte), pas de vitesse brute.

### Itération 3 — « le jeu de latence news est-il gagnable ? »

Chaîne de latence : événement → publication source → ingestion → analyse →
décision → ordre on-chain/CLOB → exécution.

Points durs :
- les sources « grand public » (presse) sont déjà en retard sur les insiders
  du domaine (comptes spécialisés, flux officiels, scanners) ;
- un LLM ajoute 1–10 s d'analyse — fatal contre des bots à règles codées en dur
  sur des événements *attendus* (résultats sportifs, chiffres macro, votes) ;
- mais sur les événements *inattendus ou ambigus* (démission surprise, jugement,
  catastrophe), la vitesse pure ne suffit pas : il faut comprendre l'implication
  → fenêtre de quelques minutes où l'analyse LLM bat les deux camps (humains
  trop lents, bots à règles aveugles).

→ Stratégie : ne PAS concourir sur les événements programmés (perdu d'avance
sans infra dédiée) ; cibler les chocs non programmés où le marché met des
minutes à se repricer, et les marchés *corrélés en second ordre* (la news
évidente bouge le marché A instantanément ; le marché B corrélé se reprice
avec retard — c'est là qu'on prend la position).

### Itération 4 — « boucle économique : l'edge survit-il aux coûts ? »

Comptabilité d'un trade : edge brut − spread − slippage − frais (gas/penny) −
coût d'inventaire (capital bloqué jusqu'à résolution) − risque oracle.

Conséquences :
- les micro-edges (<2–3 pts de proba) sur petits marchés sont mangés par le
  spread ; il faut soit des edges gros (chocs news), soit du volume (market
  making informé) ;
- le capital bloqué jusqu'à résolution rend le rendement *annualisé* sensible à
  l'horizon : un edge de 4 pts sur un marché résolu dans 9 mois est pire qu'un
  edge de 1,5 pt résolu demain ;
- le market making assisté par modèle (quotes serrées sur des marchés que
  l'agent sait pricer) transforme l'edge de calibration en flux régulier — mais
  expose à l'adverse selection exactement sur les chocs news qu'on veut chasser
  ailleurs. Les deux stratégies sont complémentaires : le module news sert aussi
  de *circuit breaker* pour le module market making (retirer les quotes quand
  une news tombe).

### Itération 5 — « risques de queue qui tuent le système »

- **Résolution UMA contestée** : un « arbitrage sûr » ne l'est que si la
  résolution est mécanique. Les marchés à règle ambiguë portent un risque
  d'oracle non diversifiable → filtre dur : score d'ambiguïté de la règle, et
  exclusion au-dessus d'un seuil.
- **ToS / géo-restrictions** : l'accès et l'automatisation dépendent de la
  juridiction ; à traiter comme contrainte de conformité de premier ordre, pas
  comme détail.
- **Décay de l'edge** : tout edge publié/observable se fait copier ; le système
  doit mesurer son propre alpha par stratégie et couper ce qui ne paie plus
  (méta-boucle d'allocation).

### Itération 6 — « le flux des autres traders est lui-même un signal »

Particularité unique de Polymarket vs un marché classique : **tout le flux est
on-chain et pseudonyme mais public**. Chaque wallet, chaque fill, chaque
position est lisible. Donc :

- un **insider** qui trade laisse une empreinte : wallet neuf (ou dormant),
  financé récemment, qui prend une position directionnelle agressive et
  démesurée sur UN marché obscur, souvent peu avant l'événement. C'est un
  pattern détectable algorithmiquement (fraîcheur du wallet × concentration ×
  agressivité × obscurité du marché) ;
- inversement, les **smart wallets** (PnL historique élevé, calibration
  démontrée sur N marchés) sont identifiables et suivables — le « copy-trading
  pondéré par la crédibilité » est une stratégie en soi ;
- le détecteur d'insiders a un double usage **offensif** (suivre le flux
  informé = acheter de l'information que quelqu'un d'autre a payée) et
  **défensif** (le module market making retire ses quotes quand un flux toxique
  arrive — c'est de l'anti-adverse-selection).

Limites à vérifier en recherche : taux de faux positifs (les degens riches
ressemblent à des insiders), latence d'indexation des données on-chain,
légalité/éthique du suivi (a priori : données publiques), et le fait que les
insiders sophistiqués fragmentent leurs wallets (→ clustering par source de
financement nécessaire).

### Synthèse du loop thinking (avant intégration des sources)

| Stratégie | Edge | Rôle de l'IA | Concurrence | Verdict |
|---|---|---|---|---|
| Arb YES+NO / neg-risk | structurel, petit | faible (scanner) | bots infra | opportuniste seulement |
| Latence news programmée | vitesse | négatif (trop lent) | très forte | éviter |
| Chocs news non programmés + 2nd ordre | compréhension | fort | moyenne | **cœur du système** |
| Lecture des règles de résolution | sémantique | fort | faible | **edge le plus défendable** |
| Longue traîne mal pricée | largeur | fort | faible | bon complément |
| Market making informé | flux | moyen | forte sur gros marchés | sur marchés moyens, avec circuit breaker news |
| Détection de flux informé / insiders (on-chain) | information d'autrui | fort (pattern + contexte) | faible-moyenne | **signal offensif + défensif** |
| Copy-trading pondéré des smart wallets | calibration d'autrui | moyen (scoring) | moyenne | complément passif |

---

## 2. Recherche vérifiée (multi-sources)

> EN COURS — résultats du harnais deep-research (recherche parallèle,
> vérification adversariale des claims, citations) à intégrer ici.

### 2.1 Mécanique Polymarket (CLOB, frais, oracle UMA, neg-risk)
*(à compléter)*

### 2.2 Classes d'arbitrage documentées
*(à compléter)*

### 2.3 Latence news & bots existants
*(à compléter)*

### 2.4 Architectures d'agents & outillage open source
*(à compléter)*

### 2.5 Économie réaliste
*(à compléter)*

### 2.6 Risques & cadre réglementaire 2025–2026
*(à compléter)*

### 2.7 Détection d'insiders / flux informé (on-chain)

#### a) Transparence des données : tout le flux est public

- Chaque trade, fill, position et wallet est lisible on-chain (contrats CTF
  Exchange sur Polygon). ⚠️ Migration v2 le 28/04/2026 : l'ancien subgraph
  Goldsky est déprécié — les pipelines legacy renvoient des données incomplètes.
  [Goldsky docs](https://docs.goldsky.com/chains/polymarket) — confiance HAUTE.
- **Data API** (`data-api.polymarket.com`, lecture sans auth) : `/positions?user=`,
  `/trades` (filtrable par marché, user, côté taker, taille), `/holders?market=`,
  `/leaderboard` — suffisant pour profiler n'importe quel wallet et surveiller
  les gros fills en quasi temps réel (500 lignes/req).
  [docs.polymarket.com](https://docs.polymarket.com/developers/misc-endpoints/data-api-get-positions) — HAUTE.
- **Goldsky v2 datasets** officiels (positions, open interest, fills) — vendus
  explicitement pour construire leaderboards PnL, whale monitors et bots de
  copy-trading. [goldsky.com/blog/polymarket-dataset](https://goldsky.com/blog/polymarket-dataset) — HAUTE.
- **Dune Analytics** : dashboards communautaires forkables (« Polymarket Whale
  Tracker », « Trader Cashflow PnL ») + alertes Dune = whale-feed gratuit. — HAUTE.
- ⚠️ Depuis avril 2026, Polymarket fait de la surveillance insider en interne
  (partenariat **Chainalysis**) : un wallet flaggé peut être gelé/annulé — le
  signal « suivre l'insider » porte donc un risque de contrepartie croissant.
  [cryptobriefing.com](https://cryptobriefing.com/polymarket-insider-trading-detection-tools/) — HAUTE.

#### b) Cas documentés (2024–2026) — et leur signature de détection

| Cas | Date | Gain | Signature détectable |
|---|---|---|---|
| Google « Year in Search » (AlphaRaccoon, 1ʳᵉ inculpation DOJ) | mai 2026 | ~1,2 M$ / 2,7 M$ misés | un seul compte balaie plusieurs marchés Google obscurs à cotes improbables |
| Sergent US — capture de Maduro | avr. 2026 | >400 k$ | financement frais (~35 k$) une semaine avant + 13 trades concentrés pré-événement classifié |
| Frappe Iran (6 wallets frais, ~1,2 M$) | févr. 2026 | ~485 k$ (top wallet) | wallets neufs, YES pas cher, **71 min** avant la frappe ; 80+ comptes suspects |
| Nobel de la paix (Machado) | oct. 2025 | ~90 k$ | compte frais « 6741 », cote 0,08 → 1,00 $ en quelques heures sans catalyseur public |
| OpenAI browser / GPT-5.2 | oct.–déc. 2025 | 7–13 k$ | wallet neuf + 40 k$ directionnel sur marché tech ; flaggé EN DIRECT par Polysights |
| Théo, la « baleine française » (élection 2024) | nov. 2024 | ~85 M$ | 11 wallets clusterisés par source de financement — mais **informé ≠ insider** : sondages « neighbor polling » commandés en privé |

Leçon clé (cas Théo) : les wallets les plus profitables tiennent parfois une
*recherche supérieure légale*, pas une fuite — les deux types de flux sont des
signaux, mais avec des cinétiques différentes.

#### c) Méthodologies de détection (du plus simple au plus robuste)

1. **Fresh-wallet detection** (la signature n°1 de TOUS les cas documentés) :
   wallet sans historique + financé via CEX depuis peu + pari directionnel
   massif sur marché de niche peu liquide + proche de la résolution.
   Implémentations open source : `pselamy/polymarket-insider-tracker`. — HAUTE.
2. **Seuils praticiens** (PolyTrack, heuristiques non validées — MOYENNE) :
   volume 5–10× la baseline en heures pré-annonce ; flux >95 % unilatéral sans
   catalyseur ; entrées 30 min–2 h avant la news ; win rate catégorie >75–80 % ;
   position = 40–60 % du capital du wallet ou 5–10× sa taille habituelle.
3. **Clustering de wallets** : source de financement commune, trades synchronisés
   à quelques minutes, sizing identique/proportionnel, création quasi simultanée
   (c'est ainsi que les 11 comptes de Théo et le cluster Iran ont été liés). — HAUTE.
4. **Screening statistique** : Mitts & Ofir (Harvard Law, mars 2026) — score
   composite (taille relative, profitabilité, timing pré-événement, concentration
   directionnelle) sur 93 000 marchés → ~210 718 paires wallet-marché flaggées,
   win rate 69,9 %, ~143 M$ de profits anormaux. Important : on score des paires
   **wallet × marché**, pas des wallets (un insider n'est informé que sur UN
   événement). Gomez-Cram et al. : 3,14 % de comptes « skilled », 1 950 comptes
   au pattern de cycle de vie insider (wallet frais → un gros pari → retrait).
   Nechepurenko (arXiv 2026) : Information Leakage Score par marché.
   [arxiv.org/abs/2605.02287](https://arxiv.org/abs/2605.02287) — HAUTE.
5. **Toxicité du flux (VPIN adapté)** : le concept (flux taker unilatéral
   soutenu = flux toxique) se transpose au CLOB Polymarket (flag taker dans la
   Data API), mais aucune étude VPIN-sur-Polymarket publiée — prometteur, non
   validé. — MOYENNE.
6. **Profilage smart-money** : leaderboards PnL + win rate conditionnel par
   catégorie (Data API `/leaderboard`, HashDive « Smart Scores »). Gizmodo
   rapporte ~85 % des trades flaggés par Polysights comme profitables → le flux
   flaggé est une source d'alpha exploitable, pas seulement du bruit compliance. — HAUTE.

#### d) Écosystème d'outils existants

- **Plateformes** : Polysights / « Insider Finder » (24 k users, flags temps réel
  sur X), PolyTrack, HashDive (Smart Scores), polymarketanalytics.com (+ bot
  Telegram PolyGun, 1 % de frais).
- **Bots Telegram copy-trading** : PolyGun, PolyCop, PolyBot (0,5–1 % de frais),
  PolyMate (« Radar » whale-flow), PolyTracker, PolyCopy — écosystème de 170+
  outils catalogués ([defiprime.com](https://defiprime.com/definitive-guide-to-the-polymarket-ecosystem)).
- **Repos open source de départ** : `suislanchez/polymarket-insider-detector`
  (p-values, timing, clustering), `pselamy/polymarket-insider-tracker`,
  `warproxxx/poly_data` (bulk data), `harish-garg/Awesome-Polymarket-Tools`.

#### e) Implications pour l'agent

1. Signal composite à plus haute précision (validé par tous les cas 2025-26) :
   **wallet frais + financement CEX récent + pari >10 k$ à cote longshot +
   marché de niche + timing pré-résolution** → copier VITE : le repricing prend
   de quelques minutes à quelques heures (Nobel : 8 ¢ → 1 $ en heures ; Iran :
   71 min de fenêtre).
2. Distinguer **insider** (pattern one-shot, retrait après gain → signal
   déclencheur d'événement) et **skilled** (~3 % des comptes, edge persistant
   multi-marchés → cible de copy-trading long terme).
3. Risque croissant : inculpations DOJ, surveillance Chainalysis, enquête du
   Congrès → un flux flaggé peut être annulé/gelé ; traiter le signal insider
   comme **décroissant et sensible réputationnellement**.
4. Stack data : Data API (temps réel) + Goldsky v2 (firehose) + Dune (backtest
   et recherche de clusters).

### 2.8 Autres sources de stratégies (biais comportementaux, modèles quantitatifs)

#### a) Inefficiences comportementales documentées

1. **Favorite-longshot bias** — l'edge le mieux documenté académiquement.
   Sur Kalshi, les contrats <10 ¢ perdent **>60 %** de la mise en moyenne ;
   rendement moyen tous contrats : **−22 %** après frais (Bürgi, Deng & Whelan).
   Une étude sur 292 M de trades (Kalshi+Polymarket, [arXiv 2602.19520](https://arxiv.org/pdf/2602.19520))
   montre que le biais se concentre sur les **horizons longs** et les **marchés
   politiques** (compressés vers 50 % par sous-confiance) ; les marchés à court
   horizon sont bien calibrés. — HAUTE.
2. **Time-decay / « theta farming »** : acheter le côté quasi certain des
   marchés longs et porter jusqu'à résolution récolte la prime de compression
   vers 50 % (explication structurelle : capital bloqué sans intérêt →
   [arXiv 2602.21091](https://arxiv.org/pdf/2602.21091)). L'edge croît avec
   l'horizon… mais le coût du capital aussi. — HAUTE (existence) / MOYENNE
   (profitabilité nette).
3. **Sous-réaction aux news publiques avec drift exploitable** :
   [arXiv 2606.07811](https://arxiv.org/abs/2606.07811) (juin 2026) — les prix
   in-game Kalshi ne bougent que **~0,64 pour 1** vs un benchmark d'information
   publique, et l'écart prédit le drift futur (coef. 0,38–0,49, significatif).
   → stratégie momentum POST-réaction initiale, distincte de la course de
   latence. — HAUTE (récent, non répliqué).
4. **Biais « overbet YES »** : Bartlett & O'Hara ([SSRN 6615739](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6615739)) —
   les traders sur-misent systématiquement YES dans des marchés qui résolvent
   majoritairement NO → biais systématique côté NO sur les marchés retail
   single-name. — HAUTE.
5. **Distorsion par baleine / biais partisan** : oct. 2024, Théo a poussé le prix
   Trump 10–15 pts au-dessus de PredictIt/Kalshi — l'écart cross-platform était
   en soi un signal de fade/arb. — HAUTE.
6. Effets week-end / nombres ronds : **non démontrés** sur les prediction
   markets (lore praticien seulement). — FAIBLE.

#### b) Stratégies cross-market

- Spreads persistants **1–5 %** Kalshi ↔ Polymarket sur événements identiques.
  Causes structurelles : bases d'utilisateurs différentes, frais (Kalshi ~0,7 % ;
  Polymarket Intl 2 % sur gains nets ; Betfair ~5 %), géo-restrictions, frictions
  de capital, et surtout **risque de divergence de résolution** (mêmes événements,
  critères différents → l'« arb sans risque » peut devenir une perte totale). — HAUTE.
- Outils publics : Oddpool, arbcalculator.cc, actor Apify « Polymarket+Kalshi
  Arb Finder ». L'edge résiduel après concurrence des bots : MOYENNE.
- Vs sportsbooks : l'overround Polymarket/Kalshi (~100–100,5 %) vs Pinnacle
  (~102 %) et retail (105–108 %) rend exécutables des edges de modèle marginaux ;
  benchmark = closing line dé-viggée. — HAUTE.
- **~40 M$ de profits d'arb réalisés** mesurés on-chain sur Polymarket
  (Market-Rebalancing + Combinatorial, [arXiv 2508.03474](https://arxiv.org/abs/2508.03474))
  → l'arb intra-plateforme était réel ET est déjà industrialisé. — HAUTE.

#### c) Market making sur Polymarket

- **Liquidity Rewards** : récompenses quotidiennes pour ordres au repos près du
  mid (formule dYdX adaptée, score quadratique en proximité du mid ; coter
  **2 côtés ≈ 3×** les rewards d'un seul côté).
  [docs officiels](https://docs.polymarket.com/developers/market-makers/liquidity-rewards). — HAUTE.
- Postmortem praticien (tezlee) : bot MM cloné → **net zéro** : rewards + spread
  mangés par l'adverse selection (« un move adverse de 30–40 % efface des
  semaines de gains en minutes »), bugs d'inventaire, impossibilité de hedger en
  carnet mince. D'autres rapportent 700–800 $/jour au pic du rewards farming. — HAUTE.
- Bartlett & O'Hara : la toxicité du flux (type VPIN) prédit les pertes des
  makers sur les marchés single-name, MAIS le sur-pari YES retail y subventionne
  les makers (**2× par contrat**). — HAUTE.
- Primitive spécifique Polymarket : **merge YES+NO → 1 $ USDC** on-chain sans
  slippage = outil de gestion d'inventaire du MM. — HAUTE.

#### d) Modèles quantitatifs vs prix de marché

1. **Crypto binaires vs options Deribit** — le trade « modèle » le plus propre :
   les marchés « BTC above X by date » sont des options digitales ; comparer au
   N(d2) extrait de la surface de vol Deribit (SSVI + Breeden-Litzenberger).
   Écarts typiques de quelques points ; implémentation open source avec
   backtester : [djienne/POLYMARKET_UP_DOWN_DERIBIT_STRATEGY](https://github.com/djienne/POLYMARKET_UP_DOWN_DERIBIT_STRATEGY). — HAUTE.
2. **Météo** : ensembles ECMWF/GFS/ICON vs buckets de température ; entrer quand
   proba modèle − prix ≥ 8–15 pts à ≤48 h. ⚠️ la fenêtre de latence post-run
   (GFS 00/06/12/18Z) s'est compressée de 30–60 min (2024) à **5–15 min (2026)**
   sur les villes liquides — l'edge décroît. — MOYENNE-HAUTE.
3. **Sports** : modèles Elo/Poisson vs marchés, rendus exécutables par le faible
   overround (cf. b). — MOYENNE.
4. **Sondages vs marché (politique)** : le trade « fade le marché vers le
   modèle » a PERDU en 2024 (marché Brier 0,185, 6/8 swing states) ; la version
   robuste est le trade d'écart **cross-platform**, pas modèle-vs-marché. — HAUTE
   (faits) / FAIBLE (supériorité des modèles de sondage).

#### e) LLM forecasting vs marchés (calibration)

- Benchmarks Metaculus 2024→2026 : les bots IA ont comblé une grande partie de
  l'écart avec la foule humaine, mais restent **moins bien calibrés** et moins
  discriminants que les pros — or la calibration EST la quantité tradable. — HAUTE.
- « Wisdom of the Silicon Crowd » (Schoenegger et al. 2024) : un **ensemble de
  12 LLMs** est statistiquement indistinguable de la foule humaine → source de
  proba bon marché à comparer au prix. Compétence **dépendante du domaine**
  ([arXiv 2511.18394](https://arxiv.org/pdf/2511.18394)) → déploiement sélectif. — HAUTE.
- Les agents IA seraient déjà une grosse fraction du flux Polymarket (14/20 top
  wallets, >30 % de l'activité selon des posts 2026) ; les PnL spectaculaires
  rapportés sont **promotionnels et non audités**. — FAIBLE (chiffres) /
  MOYENNE (tendance à la domination des bots).

#### f) Réalité de base à garder en tête

- Seuls **~0,51 % des wallets** Polymarket ont jamais réalisé >1 000 $ de profit
  net ([polymarketanalytics.com](https://polymarketanalytics.com/traders)). — MOYENNE.
- « Why 77 % win-rate traders go broke » : vendre des longshots donne un win
  rate élevé avec des pertes de queue catastrophiques → le sizing (Kelly
  fractionné) n'est pas un détail, c'est la condition de survie. — MOYENNE.

---

## 3. Architecture cible du système d'agents
*(à compléter après intégration des sources — pipeline ingestion → analyse →
pricing → exécution → post-mortem, avec boucles de feedback.)*

## 4. Plan de validation incrémental
*(à compléter — paper trading, mesure d'alpha par stratégie, kill switches.)*
