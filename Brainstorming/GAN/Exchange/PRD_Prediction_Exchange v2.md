# PRD — Prediction Exchange
**Arène multi-agents LLM sur marchés prédictifs simulés**

| | |
|---|---|
| Version | 1.0 (spécification fonctionnelle consolidée) |
| Date | 27 août 2026 |
| Statut | À valider |
| Portée | MVP → v1 (jalons M0 à M5) |

---

## 1. Contexte & vision

Prediction Exchange est une arène compétitive où des agents LLM tradent des contrats binaires sur l'issue d'événements, dans un carnet d'ordres fermé partagé. Chaque agent dispose d'un capital, d'objectifs propres et d'une **information partielle et asymétrique** (news publiques bruitées + signaux privés). Le moteur de simulation est l'unique arbitre : matching, comptabilité et résolution des événements sont déterministes, et **aucune métrique ne dépend d'un juge LLM**.

Le produit sert trois usages : (1) **benchmark** — mesurer et comparer des modèles/harness sur le raisonnement probabiliste, la lecture des prix et la gestion du risque ; (2) **banc d'optimisation** — améliorer automatiquement des agents via tournois, TrueSkill, Hall of Fame, MAP-Elites et mutation réflexive ; (3) **spectacle** — des replays lisibles où l'on voit les cotes bouger, les agents réagir aux news et le classement se faire.

Le choix du domaine est motivé par la réalité du terrain : les marchés prédictifs réels sont déjà massivement investis par des agents autonomes, et les évaluations existantes (type PolyBench/PrediBench) montrent qu'une minorité de modèles y est rentable. L'arène simulée ajoute ce que le réel ne permet pas : reproductibilité, contrôle de l'information, scénarios held-out sans contamination, et adversaires choisis.

**Modèle conceptuel.** Trois boucles imbriquées : la *boucle de tick* (état latent → observations bruitées → croyances des agents → deux canaux d'expression : prédictions déclarées scorées au Brier, ordres scorés au PnL → le prix public redevient une information) ; la *boucle de match* (oracle → règlement → métriques projetées du journal) ; la *boucle méta* (tournois → ratings → sélection/mutation des harness). Le coût d'expression d'une croyance est le spread du carnet ; il est fixé de facto par le teneur de marché de référence (§5.8), qui est donc le réglage de difficulté central de l'arène.

## 2. Objectifs & non-objectifs

### 2.1 Objectifs (v1)
- **O1 — Déterminisme total** : un match rejoué avec le même seed et les mêmes agents scriptés produit un journal identique bit à bit.
- **O2 — Évaluation 100 % objective** : PnL, Brier, drawdown, descripteurs comportementaux, tous calculés depuis l'état du simulateur.
- **O3 — Tournois industrialisés** : ≥ 100 matchs par nuit, multi-seeds, rapport automatique, coût plafonné.
- **O4 — Boucle d'amélioration démontrée** : au moins une itération de mutation réflexive produisant un gain TrueSkill mesurable sur scénarios held-out.
- **O5 — Replay grand public** : un non-initié comprend qui gagne et pourquoi en moins de 30 secondes.

### 2.2 Non-objectifs (v1)
- Pas d'argent réel ni de connexion aux plateformes réelles (Polymarket, Kalshi).
- Pas de marchés scalaires ou catégoriels (v1 = binaires uniquement) ; pas d'AMM (v1 = carnet d'ordres + teneur de marché de référence).
- Pas de fine-tuning/RL des modèles (l'optimisation porte sur prompts, harness, configs).
- Pas de SaaS multi-tenant ; usage interne mono-équipe.

## 3. Utilisateurs & cas d'usage

| Persona | Besoin principal | Cas d'usage clés |
|---|---|---|
| **Builder** (concepteur d'agents) | Itérer vite sur harness/prompts | Lancer un tournoi, lire un rapport, inspecter les traces d'un match perdu, pousser une mutation |
| **Spectateur** | Comprendre sans expertise | Ouvrir un replay partagé, suivre la course de PnL, lire le journal des décisions |
| **Chercheur** | Données propres | Exporter trades/prédictions, courbes de calibration, index de collusion, comparer modèles |

## 4. Glossaire

- **Scénario / Monde** : un univers généré (variables latentes + calendrier d'information + issues) à partir d'un seed.
- **Événement** : fait futur à issue binaire (résolue OUI/NON par l'oracle au tick de résolution du marché).
- **Marché** : carnet d'ordres sur un événement ; contrat payant 100 ¢ si OUI, 0 sinon ; prix cotés de 1 à 99 ¢.
- **Tick** : pas de temps discret, déroulé en quatre phases (§5.1). À chaque tick, les agents observent puis agissent ; le moteur exécute.
- **Signal privé** : observation bruitée de l'état latent, distribuée à un agent spécifique.
- **Prior public** : probabilité d'ouverture d'un marché, connue de tous au tick 1 (FR-5.2.4).
- **Mid** : moyenne des meilleures limites (best bid + best ask) / 2, définie seulement si le carnet est bilatéral.
- **Prix de référence** : mid si carnet bilatéral, sinon dernier prix exécuté, sinon prior public (FR-5.4.6). Sert au mark-to-market, à la bande de protection et au teneur de marché.
- **Mark-to-market (MTM)** : valorisation des positions au prix de référence, à chaque clôture de tick.
- **Maker / Taker** : ordre au repos dans le carnet / ordre entrant qui le croise. Une exécution a lieu au prix du maker.
- **Collatéral** : cash séquestré garantissant la pire perte possible d'un ordre ou d'une position (FR-5.5.1).
- **Teneur de marché de référence (MM)** : agent scripté neutre, non informé et hors classement, qui garantit la liquidité (§5.8).
- **Profil de liquidité** : preset de paramètres du MM (liquide / standard / illiquide) qui règle la difficulté d'un scénario.
- **Harness** : le couple {modèle, prompt système, stratégie de contexte, paramètres} versionné, qui définit un agent.
- **Match** : 1 scénario × N agents × T ticks, suivi de la résolution et du règlement.
- **Matchup** : combinaison d'agents comparée sur plusieurs seeds.

## 5. Design du jeu (règles fonctionnelles)

### 5.1 Boucle de match — modèle en phases

Un match = 1 scénario (seed) × N agents × T ticks. Chaque tick se déroule en quatre phases strictement ordonnées :

| Phase | Nom | Contenu |
|---|---|---|
| **P1** | Diffusion | L'info-engine publie les news du tick et distribue les signaux privés ; les marchés arrivés à leur tick de résolution sont résolus et réglés, l'issue étant publiée comme news ; les observations sont construites. |
| **P2** | Décision | Les agents sont appelés en parallèle avec timeout ; leurs actions sont validées (JSON Schema). |
| **P3** | Exécution | Le MM recote en premier, hors tirage (FR-5.8.1) ; puis l'ordre de passage des agents est mélangé (shuffle seedé) et les actions de chaque agent s'appliquent atomiquement, dans l'ordre soumis, contre le carnet. |
| **P4** | Clôture | Mark-to-market, snapshots, métriques incrémentales, écriture du journal. |

- **FR-5.1.1** Un agent qui ne répond pas (timeout, JSON invalide) est traité comme « aucune action » ; ses prédictions sont reportées (FR-6.2.4) ; l'incident est loggé, le match continue.
- **FR-5.1.2** Le moteur n'appelle jamais de LLM ; toute intelligence est côté agents.
- **FR-5.1.3** Event sourcing : tout l'historique d'un match est rejouable depuis le journal d'événements seul.
- **FR-5.1.4** L'ordre des phases et le traitement intra-phase sont entièrement déterministes à seed fixé.
- **FR-5.1.5** Le shuffle d'équité de P3 est dérivé du RNG racine par (seed, numéro de tick).

### 5.2 Génération de mondes — deux modes

**Mode A — Synthétique (défaut, v1)** : gabarits de mondes à variables latentes, par exemple :
- *Élection fictive* : forces latentes des candidats + sondages bruités publiés au fil des ticks.
- *Rendement/météo* : processus latent saisonnier + relevés partiels.
- *Championnat fictif* : forces d'équipes cachées + résultats de matchs intermédiaires (marchés à résolution anticipée).

Le ground truth est simulé par un processus stochastique seedé ; news et signaux sont des observations bruitées de l'état latent. Avantages : zéro contamination des modèles, difficulté paramétrable, génération infinie de scénarios held-out.

**Mode B — Replay historique (v2)** : événements réels post-cutoff avec flux d'actualités horodaté, réservés à l'évaluation held-out. Hors périmètre MVP.

- **FR-5.2.1** De 2 à 8 marchés par monde, avec **corrélations** entre événements (ex. « A gagne » et « participation > 60 % ») pour créer des arbitrages de cohérence.
- **FR-5.2.2** Sur 10 000 tirages d'un gabarit, la fréquence des issues converge vers les probabilités latentes (test statistique automatisé).
- **FR-5.2.3** Chaque marché possède son **propre tick de résolution** (défaut : dernier tick T). Une résolution anticipée clôt le trading sur ce marché, libère le collatéral et est annoncée en P1 du tick concerné.
- **FR-5.2.4** Chaque marché est doté d'un **prior public** d'ouverture (défaut : 50 ¢), défini par le gabarit et visible de tous au tick 1 ; il sert de prix de référence initial (FR-5.4.6).

### 5.3 Information
- News publiques : visibles de tous au même tick, qualité variable (certaines sont du bruit pur) ; l'info-engine tague chaque news d'un niveau d'impact (utilisé notamment par FR-5.8.4).
- Signaux privés : chaque agent tire 0 à 2 signaux par tick selon son **profil informationnel** (généraliste, spécialiste d'un événement, retardé).
- **FR-5.3.1** Un agent bayésien scripté exploitant ses signaux doit battre un agent aléatoire sur 1 000 matchs (test de « valeur de l'information »).
- **FR-5.3.2** En tournoi noté, les profils informationnels sont permutés entre agents selon un **carré latin** sur les seeds du matchup : chaque harness occupe chaque profil un nombre égal de fois.

### 5.4 Marchés & carnet d'ordres
- **FR-5.4.1** Carnet central à double enchère continue (CLOB), priorité prix-temps, exécutions partielles ; une exécution a lieu au prix de l'ordre au repos (maker).
- **FR-5.4.2** Types d'ordres : `limit` (GTC : persiste jusqu'à exécution, annulation explicite ou clôture du marché), `market`, `cancel`. Plafond de **10 ordres actifs par agent et par marché** ; tout ordre excédentaire est rejeté avec motif.
- **FR-5.4.3** Un ordre `market` est converti en limite « marketable » bornée à **± 10 ¢ autour du prix de référence** (bande de protection) ; la quantité non exécutable dans la bande est annulée, jamais laissée au repos.
- **FR-5.4.4** Prévention d'auto-exécution (STP) : un ordre entrant qui croiserait un ordre au repos du même agent **annule l'ordre au repos** au lieu de le matcher ; l'événement est loggé. Le wash trading économique entre complices reste du ressort des détecteurs d'intégrité (§7.5).
- **FR-5.4.5** Prix admis : 1–99 ¢, pas de 1 ¢. Aucun trading sur un marché résolu ou annulé. Un marché ne peut être annulé que par le script du scénario ; l'annulation dénoue toutes les exécutions et restitue le cash.
- **FR-5.4.6** **Prix de référence** d'un marché : mid si le carnet est bilatéral ; sinon dernier prix exécuté ; sinon prior public (FR-5.2.4). Utilisé pour le MTM (FR-5.5.4), la bande de protection (FR-5.4.3) et la cotation du MM (§5.8).
- **FR-5.4.7** Frais taker paramétrables (défaut 0 % ; jusqu'à 2 %), versés à une caisse hors classement ; aucun frais maker.

### 5.5 Comptabilité, collatéral, règlement
- **FR-5.5.1** Formules de collatéral : achat à p ¢ → **p × qté** ; vente (y compris à découvert) à p ¢ → **(100 − p) × qté**. Le collatéral est **réservé dès le placement** de l'ordre, libéré à l'annulation, transformé à l'exécution.
- **FR-5.5.2** Pas de compensation inter-marchés en v1 : le collatéral requis est la somme des pires cas par marché.
- **FR-5.5.3** Système fermé : la position nette agrégée de chaque marché est nulle ; la somme des cash de tous les comptes (agents + MM + caisse des frais) est constante ; chaque exécution et chaque règlement sont à somme nulle entre comptes. Ces invariants sont vérifiés à chaque tick (tests de propriété).
- **FR-5.5.4** MTM au prix de référence (FR-5.4.6) à chaque P4 ; le **classement final** est calculé après règlement par l'oracle, jamais au MTM.
- **FR-5.5.5** Un ordre qui excéderait le collatéral libre est rejeté (aucun solde négatif possible). Faillite (cash et collatéral libres épuisés) : ordres annulés, agent gelé jusqu'à la fin, classé sur son résultat final.

### 5.6 Communication inter-agents (option « mode parlant »)
- **FR-5.6.1** Canal public : 1 message ≤ 280 caractères par tick et par agent ; horodaté et loggé ; livré aux autres agents au tick suivant. v1 livrée en mode « silencieux » par défaut ; le mode parlant est un flag de scénario (axe recherche collusion/persuasion, §7.5).
- **FR-5.6.2** Les messages sont la **seule** surface d'injection entre agents : affichés comme données non fiables, tronqués et échappés ; le moteur ne les interprète jamais.

### 5.7 Paramètres par défaut

| Paramètre | Défaut | Plage |
|---|---|---|
| Agents par match | 6 | 4–8 |
| Ticks par match | 48 | 24–96 |
| Marchés par monde | 5 | 2–8 |
| Cash initial | 10 000 | fixe par tournoi |
| Frais taker | 0 % | 0–2 % |
| Signaux privés / tick / agent | 0–2 | param. scénario |
| Ordres actifs max / agent / marché | 10 | 5–20 |
| Bande de protection `market` | ± 10 ¢ | 5–20 ¢ |
| Prior public d'ouverture | 50 ¢ | défini par gabarit |
| Tick de résolution par marché | T (final) | 1–T |
| Profil de liquidité (MM, §5.8) | standard | liquide / standard / illiquide |
| Mode parlant | off | on/off |
| Seeds par matchup | 3 | ≥ 3 |

### 5.8 Teneur de marché de référence (MM)

Le MM de référence est le **thermostat de liquidité** de l'arène : unique source de liquidité exogène garantie, il fixe le coût d'expression d'une croyance (le spread), donc la difficulté du jeu. Il est **non informé, neutre et hors classement**. Sa spécification est bloquante pour le jalon M1 (tâche T2.6).

- **FR-5.8.1** Cotation bilatérale à chaque tick sur chaque marché ouvert : bid = ref − s/2, ask = ref + s/2 (arrondis au tick de prix), taille q par côté ; recotation intégrale (cancel/replace) en tout début de P3, **hors shuffle**, pour que la liquidité affichée soit identique quel que soit l'ordre de passage des agents.
- **FR-5.8.2** Non informé : le MM n'accède ni aux signaux privés ni à l'état latent ; sa référence de cotation est le prix de référence public (FR-5.4.6).
- **FR-5.8.3** Gestion d'inventaire : la référence de cotation est décalée de −k × (inventaire / I_max) ¢ (réversion) ; le MM cesse de coter le côté qui porterait |inventaire| au-delà de I_max sur ce marché.
- **FR-5.8.4** Réaction aux news : après une news publique taguée « fort impact » (§5.3), le spread est doublé pendant w ticks — le MM réagit au *fait* qu'une information est tombée, jamais à son contenu.
- **FR-5.8.5** Neutralité : paramètres identiques pour tous les matchs d'un tournoi ; PnL exclu du classement et des ratings, comptabilisé séparément dans les invariants (FR-5.5.3) et publié dans les rapports (coût de la liquidité).
- **FR-5.8.6** Profils de liquidité (preset de scénario) :

| Paramètre MM | Liquide | Standard | Illiquide |
|---|---|---|---|
| Spread de base s | 4 ¢ | 6 ¢ | 12 ¢ |
| Taille cotée q (contrats/côté) | 50 | 25 | 10 |
| Inventaire max I_max (contrats/marché) | 500 | 300 | 150 |
| Skew d'inventaire k | 2 ¢ | 4 ¢ | 8 ¢ |
| Élargissement post-news w | 1 tick | 2 ticks | 3 ticks |

## 6. Contrats d'interface agents

### 6.1 Observation (moteur → agent)
JSON versionné (`obs_version`), compact (budget cible < 2 000 tokens au tick médian) : tick courant, news publiques du tick, signaux privés, par marché {prix de référence, mid s'il existe, best_bid, best_ask, profondeur agrégée 3 niveaux, dernier prix, prior public, tick de résolution, mes positions}, cash, collatéral libre, mes ordres actifs, mini-historique des prix de référence (sparkline numérique), messages publics du tick précédent (si mode parlant).

### 6.2 Action (agent → moteur)
```json
{
  "action_version": "1.0",
  "predictions": [
    {"market_id": "M1", "p_yes": 0.62},
    {"market_id": "M2", "p_yes": 0.18}
  ],
  "orders": [
    {"op": "place", "market_id": "M1", "side": "buy", "type": "limit", "price": 58, "qty": 40},
    {"op": "cancel", "order_id": "o-1234"}
  ],
  "message_public": null
}
```
Règles :
- **FR-6.2.1** `predictions` est **obligatoire** pour chaque marché ouvert (score de Brier ; découplé du PnL, §7.2).
- **FR-6.2.2** Validation stricte par JSON Schema ; toute action partiellement invalide est tronquée aux éléments valides, le reste rejeté avec motif loggé.
- **FR-6.2.3** Le harness a droit à un budget de tokens et un timeout par tick, configurés par tournoi.
- **FR-6.2.4** Prédiction manquante ou invalide pour un marché ouvert ⇒ **report de la dernière valeur déclarée** (0,50 par défaut au premier tick) ; les valeurs reportées comptent dans le Brier et sont marquées `carried` dans le journal.

## 7. Métriques & évaluation

### 7.1 Performance (par match)
- **PnL final** (après règlement), en ¢ et en % du capital initial — métrique de classement principale.
- **Rendement ajusté** : PnL / écart-type du PnL mark-to-market par tick (proxy de Sharpe).
- **Drawdown max** intra-match (sur la trajectoire MTM, prix de référence FR-5.4.6).
- **Volume, nombre de trades, frais payés**.

### 7.2 Calibration (découplée du PnL)
- **Score de Brier** : moyenne uniforme de (p_déclarée − issue)² sur l'ensemble {ticks où le marché est ouvert} × {marchés} ; un marché cesse de compter après son tick de résolution ; les valeurs reportées (FR-6.2.4) comptent. Courbes de fiabilité par agent.
- Principe anti-hacking : le Brier est calculé uniquement sur les prédictions déclarées, le PnL uniquement sur les trades ; **aucun score n'entre dans le calcul de l'autre**. L'incohérence prédiction/position (ex. déclarer 0,80 et vendre massivement) est un descripteur d'intégrité (§7.5), pas une pénalité de score.

### 7.3 Ratings
- **TrueSkill** mis à jour sur le classement PnL de chaque match (gère 4–8 joueurs et les équipes futures) ; μ et σ suivis par version de harness. Le MM de référence n'est jamais raté (FR-5.8.5).
- Chaque matchup est joué sur ≥ 3 seeds avec permutation des profils informationnels (FR-5.3.2) ; les rapports affichent des intervalles de confiance bootstrap.

### 7.4 Descripteurs comportementaux (axes MAP-Elites)
Calculés exclusivement depuis le journal : part d'ordres passifs (maker ratio), latence de réaction à l'information (ticks entre signal et premier trade lié), horizon moyen de détention, concentration du portefeuille (Herfindahl par marché), utilisation du collatéral (levier effectif), intensité de communication (mode parlant).

### 7.5 Intégrité & anti-reward-hacking
- **Index de collusion** : corrélation nette des flux entre paires d'agents + détection de transferts de richesse par trades éloignés du prix de référence (> k écarts-types).
- **Wash trading économique** (aller-retours entre complices), **spoofing** (ratio annulations/exécutions anormal), **incohérence prédiction/position**. L'auto-exécution naïve est déjà bloquée au niveau moteur (FR-5.4.4).
- Chaque alerte crée un `incident` horodaté, visible dans les rapports ; les seuils sont étalonnés sur un banc de test avec agents tricheurs scriptés (T5.5).

## 8. Tournois & optimisation

- **Formats** : round-robin (petites populations), système suisse (grandes populations), matchs d'exhibition.
- **Population d'arrière-plan** : le MM de référence (§5.8, hors classement) + 4 baselines scriptées classées — fondamentaliste bruité, momentum, noise trader, zero-intelligence — servant de planchers TrueSkill.
- **Hall of Fame** : versions de harness gelées (config + prompt hashés), réinjectées comme adversaires.
- **Failure Hall of Fame** : couples (scénario, seed) où le champion courant sous-performe le plus ; rejoués à chaque itération.
- **MAP-Elites** : grille 2–3 D sur les descripteurs §7.4 ; l'élite d'une cellule est la version au meilleur μ TrueSkill présentant ce style.
- **Held-out** : banque de scénarios scellés (jamais vus pendant l'itération), générés par les mêmes gabarits avec seeds réservés ; tout accès est journalisé.
- **Mutation réflexive** : pipeline hors-ligne qui lit les traces des pires matchs d'un harness, propose un patch (prompt/config), crée une nouvelle version, la fait valider par tournoi A/B, et ne promeut que sur gain held-out.

## 9. Visualisation & replay

- **Vue match** : un panneau par marché (cote en ¢ dans le temps, carnet simplifié), bandeau de news défilant, badges des signaux privés révélés a posteriori (spectateur omniscient en replay).
- **Course de PnL** : lignes colorées par agent, classement en direct, événements marquants annotés (gros trade, résolution anticipée, alerte d'intégrité).
- **Journal des décisions** : par tick et par agent — prédictions, ordres, message public, extrait de raisonnement du harness (si fourni), avec recherche.
- **Replay** : x1 à x64, accès aléatoire par tick, URL partageable en lecture seule.
- **Vue tournoi** : leaderboard TrueSkill avec incertitude, grille MAP-Elites, courbes de progression par version, alertes d'intégrité, coût de la liquidité (PnL du MM).

## 10. Architecture technique

### 10.1 Principes
1. **Déterminisme** : un seul RNG racine seedé, dérivé par composant ; aucun accès horloge/réseau dans le moteur ; ordre de traitement spécifié partout (phases §5.1).
2. **Event sourcing** : le journal append-only des événements de match est la source de vérité ; états et métriques sont des projections recalculables.
3. **Séparation stricte moteur / agents** : le moteur est pur et synchrone ; les agents (LLM ou scriptés) vivent derrière une passerelle asynchrone avec timeouts.
4. **Tout est versionné** : gabarits de mondes, schémas d'observation/action, harness, seeds — un match référence des versions exactes.

### 10.2 Modules
| Module | Responsabilité |
|---|---|
| `world-gen` | Gabarits de mondes, tirage seedé, ground truth latent, corrélations, priors publics, ticks de résolution |
| `info-engine` | Calendrier de news publiques (avec tag d'impact) et signaux privés, bruit, profils informationnels |
| `exchange` | Carnet CLOB, matching prix-temps, STP, bande de protection, comptes, collatéral, frais |
| `market-maker` | Teneur de marché de référence (§5.8), presets de liquidité |
| `oracle` | Résolution des événements (par marché, FR-5.2.3), règlement |
| `match-runner` | Boucle de phases P1–P4, validation d'actions, journal d'événements |
| `agent-gateway` | Adapters fournisseurs LLM + agents scriptés, schémas, budgets, retries |
| `tournament-orchestrator` | Matchmaking, files, multi-seeds, carré latin des profils, reprise sur erreur, coûts |
| `ratings` / `elites` | TrueSkill, archive MAP-Elites, Halls of Fame |
| `integrity` | Détecteurs collusion / wash / spoofing / incohérence, incidents |
| `store` | Postgres (métadonnées) + JSONL/Parquet (journaux, traces LLM) |
| `replay-api` | REST + WebSocket de relecture |
| `web-ui` | React : vues match, tournoi, journal, partage |

### 10.3 Stack proposée
Python 3.12 (moteur, orchestration, FastAPI), Postgres + fichiers Parquet/JSONL, `trueskill` (lib), React + Vite + WebSocket pour l'UI, exécution parallèle par processus (pas de dépendance cloud obligatoire en v1). Monorepo, CI avec tests et vérification de déterminisme.

### 10.4 Modèle de données (entités principales)
`scenario_template`, `scenario_instance(seed)`, `match`, `agent`, `harness_version`, `tick`, `news_item`, `signal`, `order`, `trade`, `position_snapshot`, `prediction`, `resolution`, `settlement`, `metric_record`, `rating_record`, `elite_cell`, `incident`, `tournament`, `heldout_registry`, `mm_config`.

### 10.5 Séquence d'un match
`tournament-orchestrator` → instancie `scenario_instance` (seed) → `match-runner` ouvre le journal → boucle P1–P4 : `info-engine` publie et `oracle` résout les marchés échus (P1) → `agent-gateway` collecte les actions en parallèle avec timeout (P2) → `market-maker` recote puis `exchange` exécute les agents mélangés (P3) → MTM et snapshot (P4) → fin de match : règlement final → `metrics`/`ratings`/`integrity` projettent → rapport.

## 11. Phasage & jalons

| Jalon | Contenu | Critère de sortie |
|---|---|---|
| **M0 — Moteur** | Epic E1 complet | AC-P1 (déterminisme) vert ; match scripté 6×48 < 5 s |
| **M1 — Agents LLM** | Epic E2, dont T2.6 (MM) | AC-P2 : premier match LLM de bout en bout **avec le MM de référence recetté** |
| **M2 — Tournois** | Epic E3 | AC-P3 : tournoi nightly 100 matchs + rapport auto |
| **M3 — Replay** | Epic E4 | AC-P7 : replay partageable compris en < 30 s |
| **M4 — Optimisation** | T5.1–T5.4 | AC-P8 : gain held-out démontré par mutation |
| **M5 — Intégrité** | T5.5–T5.6 | AC-P6 : détection collusion ≥ 0,9 précision/rappel |

## 12. WBS — tâches, dépendances, critères d'acceptance

### Epic E1 — Moteur de simulation
| ID | Tâche | Dépend de | Critères d'acceptance |
|---|---|---|---|
| T1.1 | Monorepo, CI, qualité | — | `make test` vert en CI ; lint + typage ; couverture publiée |
| T1.2 | Schéma de données & event store | T1.1 | Entités §10.4 migrées ; journal append-only ; un run se relit intégralement depuis le journal seul (FR-5.1.3) |
| T1.3 | Matching engine CLOB | T1.2 | Priorité prix-temps validée par tests golden (FR-5.4.1) ; limit GTC / market borné / cancel (FR-5.4.2, FR-5.4.3) ; STP « cancel resting » (FR-5.4.4) ; exécutions partielles ; ≥ 10 000 ordres/s en local |
| T1.4 | Comptabilité & collatéral | T1.3 | Formules FR-5.5.1 testées achat/short ; réservation au placement ; invariants FR-5.5.3 en tests de propriété ; solde négatif impossible ; faillite gèle l'agent (FR-5.5.5) |
| T1.5 | Générateur de mondes (3 gabarits) | T1.2 | Monde entièrement dérivé du seed ; 2–8 marchés corrélés (FR-5.2.1) ; priors publics et ticks de résolution par marché (FR-5.2.3, FR-5.2.4) ; test statistique FR-5.2.2 vert |
| T1.6 | Info-engine (news + signaux) | T1.5 | Calendrier paramétrable ; tags d'impact ; profils informationnels ; test « valeur de l'information » FR-5.3.1 vert |
| T1.7 | Oracle & règlement | T1.4, T1.5 | Résolution par marché au tick prévu (FR-5.2.3) ; paiements exacts au ¢ ; marché annulé = dénouement intégral (FR-5.4.5) |
| T1.8 | Match-runner déterministe (phases P1–P4) | T1.3–T1.7 | Même seed + agents scriptés → hash de journal identique sur 2 machines (FR-5.1.4, FR-5.1.5) ; match 6 agents × 48 ticks < 5 s sans LLM |

### Epic E2 — Agents & passerelle
| ID | Tâche | Dépend de | Critères d'acceptance |
|---|---|---|---|
| T2.1 | Schémas observation/action + validateur | T1.8 | JSON Schema versionnés ; action invalide → rejet motivé sans crash (FR-6.2.2) ; report des prédictions manquantes (FR-6.2.4) ; fuzzing 10 000 actions aléatoires sans exception non gérée |
| T2.2 | 4 baselines scriptées (fondamentaliste, momentum, bruit, ZI) | T2.1 | 100 matchs sans erreur chacune ; fondamentaliste > noise trader en TrueSkill (significatif) |
| T2.6 | **Market maker de référence (spec §5.8) — bloquant M1** | T2.1 | Cotation bilatérale ≥ 95 % des ticks par marché ouvert (FR-5.8.1) ; spread moyen conforme au profil ± 1 ¢ ; \|inventaire\| ≤ I_max en permanence (test de propriété, FR-5.8.3) ; élargissement post-news vérifié (FR-5.8.4) ; 3 presets recettés (FR-5.8.6) ; perte moyenne du MM mesurée et documentée sur 200 matchs de baselines |
| T2.3 | Gateway LLM multi-fournisseurs | T2.1 | ≥ 2 fournisseurs ; retries + timeout + repli « aucune action » (FR-5.1.1) ; coût tokens et latence loggés par tick et par agent |
| T2.4 | Observation builder compact | T2.3 | Observation < 2 000 tokens au tick médian ; contient 100 % des ordres actifs et positions de l'agent ; test de fidélité automatisé |
| T2.5 | Budgets & parallélisme | T2.3 | Plafond de coût par match respecté ; appels des agents parallélisés ; le timeout d'un agent n'allonge pas le tick au-delà du seuil configuré |

### Epic E3 — Tournois & ratings
| ID | Tâche | Dépend de | Critères d'acceptance |
|---|---|---|---|
| T3.1 | Orchestrateur de tournois | T1.8, T2.2, T2.6 | Round-robin et suisse ; reprise après crash sans double comptage ; 100 matchs enchaînés sans intervention ; carré latin des profils appliqué (FR-5.3.2) |
| T3.2 | Service TrueSkill | T3.1 | Mise à jour post-match sur classement PnL ; MM exclu (FR-5.8.5) ; σ décroissant ; ordre attendu des baselines retrouvé sur 200 matchs |
| T3.3 | Multi-seeds & agrégation | T3.1 | ≥ 3 seeds par matchup imposés ; intervalles de confiance bootstrap dans les rapports |
| T3.4 | Hall of Fame | T3.2 | Versions gelées (hash config+prompt) rejouables à l'identique ; réinjection en population d'arrière-plan |
| T3.5 | Banque held-out | T1.5 | Seeds scellés inaccessibles à l'itération ; tout accès journalisé ; rapports séparés train / held-out |
| T3.6 | Rapports automatiques | T3.2, T3.3 | Fin de tournoi → rapport MD/HTML auto (classement, deltas, coûts, incidents, coût de la liquidité) sans action manuelle |

### Epic E4 — UI & replay
| ID | Tâche | Dépend de | Critères d'acceptance |
|---|---|---|---|
| T4.1 | Replay API (REST + WS) | T1.8 | Streaming x1–x64 ; accès aléatoire par tick ; < 100 ms par requête sur le match de référence |
| T4.2 | Vue marchés & news | T4.1 | Cotes, carnet simplifié et bandeau news synchronisés au tick ; 8 agents distinguables ; lisible sur écran 13" |
| T4.3 | Course de PnL & leaderboard | T4.1 | PnL mark-to-market par tick ; classement final identique au règlement comptable au ¢ près |
| T4.4 | Journal des décisions | T4.1, T2.3 | Prédictions (dont `carried`), ordres, messages par agent/tick ; recherche texte ; navigation tick ↔ trade |
| T4.5 | Partage de replay | T4.2–T4.4 | URL autonome en lecture seule ; 5 testeurs non initiés identifient le gagnant et une raison en < 30 s |

### Epic E5 — Optimisation & intégrité
| ID | Tâche | Dépend de | Critères d'acceptance |
|---|---|---|---|
| T5.1 | Métriques comportementales | T1.8 | 6 descripteurs calculés du journal seul ; stabilité inter-seeds (corrélation > 0,6 pour un même harness) |
| T5.2 | Archive MAP-Elites | T5.1, T3.2 | Grille 2–3 D configurable ; élite = meilleur μ de la cellule ; visualisation de la grille dans l'UI tournoi |
| T5.3 | Failure Hall of Fame | T3.3 | Extraction auto des (scénario, seed) où le champion sous-performe > seuil ; rejouables en une commande |
| T5.4 | Mutation réflexive | T5.3, T3.6 | Pipeline traces → patch → version → A/B ; promotion uniquement sur gain held-out ; ≥ 1 itération réussie documentée |
| T5.5 | Détecteurs d'intégrité | T5.1 | Sur banc de test avec tricheurs scriptés : précision et rappel ≥ 0,9 (collusion) ; faux positifs < 5 % sur population honnête ; wash économique, spoofing et incohérence prédiction/position flaggés |
| T5.6 | Étude de calibration | T3.6 | Brier + courbes de fiabilité par modèle dans les rapports ; analyse Brier vs PnL publiée |

**Chemin critique** : T1.1 → T1.2 → T1.3 → T1.4 → T1.8 → T2.1 → {T2.3, T2.6} → T3.1 → T3.2 (le reste se parallélise : T1.5/T1.6 dès T1.2 ; E4 dès T1.8 ; E5 dès T3.x).

## 13. Critères d'acceptance produit (E2E)

- **AC-P1 Déterminisme** — Étant donné un seed et 6 agents scriptés, quand le match est exécuté deux fois (machines différentes), alors les journaux d'événements sont identiques bit à bit.
- **AC-P2 Match LLM** — Étant donné 4 agents LLM, 1 baseline et le MM de référence, quand un match 48 ticks s'exécute, alors il se termine sans intervention, toutes les actions sont validées ou rejetées proprement, et le règlement est exact au centime.
- **AC-P3 Tournoi nightly** — Étant donné une population de 8 harness, quand le tournoi nocturne est lancé, alors ≥ 100 matchs sont joués sur ≥ 3 seeds/matchup avec carré latin des profils, le coût reste sous le plafond configuré, et le rapport est généré automatiquement.
- **AC-P4 Découplage des scores** — Quand les métriques sont calculées, alors le Brier ne dépend que des prédictions déclarées et le PnL que des trades ; modifier l'un ne change pas l'autre (test).
- **AC-P5 Held-out** — Quand un harness est évalué, alors le rapport distingue performance d'itération et performance sur scénarios scellés, avec journal des accès à la banque held-out.
- **AC-P6 Intégrité** — Étant donné une paire d'agents colludeurs scriptés insérée dans un tournoi, quand les détecteurs tournent, alors un incident est levé (précision/rappel ≥ 0,9 sur le banc), et un tournoi honnête produit < 5 % de faux positifs.
- **AC-P7 Replay** — Étant donné une URL de replay, quand un non-initié l'ouvre, alors il identifie le gagnant et au moins une raison de sa victoire en < 30 s (5/5 testeurs).
- **AC-P8 Boucle d'amélioration** — Quand une itération de mutation réflexive est exécutée, alors le harness enfant gagne ≥ +1,0 μ TrueSkill vs parent sur la banque held-out, à coût par match ≤ 110 % du parent.
- **AC-P9 Liquidité garantie** — Étant donné un match sans aucun agent actif (agents muets), quand il s'exécute, alors chaque marché ouvert affiche une cotation bilatérale du MM sur ≥ 95 % des ticks et le prix de référence est défini à chaque tick.

## 14. Risques & mitigations

| Risque | Impact | Mitigation |
|---|---|---|
| Contamination (événements connus des modèles) | Scores biaisés | Mode synthétique par défaut ; l'historique réel uniquement en held-out post-cutoff |
| Variance inter-runs élevée | Classements bruités | ≥ 3 seeds/matchup, IC bootstrap, TrueSkill (σ explicite), carré latin des profils informationnels (FR-5.3.2) |
| Coût tokens | Budget | Observations compactes (T2.4), plafonds par match (T2.5), modèles économiques pour l'itération, gros modèles pour l'évaluation |
| Marchés dégénérés (personne ne trade, prix indéfinis) | Matchs illisibles, métriques cassées | MM de référence spécifié (§5.8, T2.6 bloquant M1) ; profils de liquidité ; prior public d'ouverture (FR-5.2.4) ; règle de repli du prix de référence (FR-5.4.6) |
| Slippage absurde en carnet mince | PnL aberrants | Bande de protection des ordres `market` (FR-5.4.3) |
| Reward hacking du Brier via les trades (ou inverse) | Métriques faussées | Découplage strict §7.2 + descripteur d'incohérence §7.5 |
| Wash trading trivial | Volumes et détecteurs pollués | STP au niveau moteur (FR-5.4.4) ; le wash économique reste ciblé par T5.5 |
| Collusion émergente entre agents LLM | Résultats faussés, sujet sensible | Détecteurs T5.5 ; mode parlant désactivé par défaut ; incidents visibles dans les rapports |
| Injection via messages inter-agents | Déstabilisation des harness | Messages traités comme données non fiables, tronqués, échappés (FR-5.6.2) ; moteur jamais exposé |
| Latence/pannes fournisseurs LLM | Matchs bloqués | Timeouts + action nulle + retries (FR-5.1.1) ; reprise de tournoi idempotente |

## 15. KPIs de succès

- Coût moyen par match et par tournoi (cible : paramétrable, suivi dès M1).
- Matchs/nuit (cible ≥ 100 dès M2) ; taux de matchs terminés sans incident technique ≥ 99 %.
- σ TrueSkill médian après 20 matchs d'un nouveau harness (cible : ≤ 1/3 du σ initial).
- Temps pour ajouter un nouveau gabarit de monde (cible ≤ 1 jour dès M2).
- Gain held-out cumulé de la boucle de mutation sur 5 itérations (cible : positif et monotone sur ≥ 3/5).
- Coût de la liquidité (perte moyenne du MM par match) : stable et documenté par profil.
- Engagement replay : durée médiane de visionnage d'un replay partagé.

## 16. Questions ouvertes

1. **v2 — AMM vs CLOB** : remplacer ou compléter le MM de référence par un teneur automatique type LMSR ?
2. **Marchés scalaires/catégoriels** en v2 (fourchettes de valeurs, multi-issues) ?
3. **Humains dans l'arène** : autoriser des joueurs humains dans certains matchs d'exhibition ?
4. **Mode parlant** : en faire l'axe de recherche principal (persuasion, collusion, désinformation entre agents) ou le garder secondaire ?
5. **Équipes** : matchs 2v2v2 (fonds avec analyste + trader) pour exploiter TrueSkill par équipes ?
6. **Publication** : ouvrir un leaderboard public des modèles (façon arène) une fois M3 atteint ?
7. **MM adaptatif** : faut-il un profil « MM apprenant » en v2, ou la neutralité prime-t-elle toujours ?

## 17. Historique des révisions

| Version | Date | Changements |
|---|---|---|
| 0.9 | 26/08/2026 | Draft initial complet (vision, design, architecture, WBS, AC). |
| 1.0 | 27/08/2026 | Consolidation fonctionnelle : modèle conceptuel (§1) ; glossaire complété (mid, prix de référence, MTM, collatéral, MM) ; boucle de tick en 4 phases déterministes (§5.1) ; tick de résolution et prior public par marché (FR-5.2.3/4) ; carré latin des profils informationnels (FR-5.3.2) ; cycle de vie des ordres, bande de protection `market`, STP, règle de repli du prix de référence (§5.4) ; formules de collatéral et invariants de système fermé (§5.5) ; **spec dédiée du market maker de référence (§5.8) avec profils de liquidité, promue depuis T2.2 en tâche T2.6 bloquante M1** ; report des prédictions manquantes (FR-6.2.4) ; définition précise du Brier (§7.2) ; FR systématiques et raccrochées aux AC du WBS ; AC-P9 (liquidité garantie) ; risques enrichis. |
