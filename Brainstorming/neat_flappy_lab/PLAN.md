# neat_flappy_lab — Plan détaillé

> Outil pédagogique de visualisation : une **population de réseaux de neurones**
> évolue par **NEAT** (topologie augmentée) pour jouer à un **Flappy-like**, avec
> en option un **apprentissage local par descente de gradient** (imitation des
> champions) pendant la vie de chaque agent. Le but est de **voir** l'interaction
> entre évolution globale et raffinement local.

---

## 1. Concept & objectif

- **But premier** : démo / outil pédagogique. La priorité est la *lisibilité visuelle*
  de l'interaction évolution + gradient descent, pas la performance brute.
- **Question qu'on rend visible** : « qu'apporte le gradient descent local par-dessus
  la neuroévolution pure ? » → on compare 3 régimes côte à côte sur la même tâche.
- **Tâche** : Flappy-like. Chaque agent = un oiseau piloté par un petit réseau NEAT.

### Pourquoi ce mélange a du sens (rappel du raisonnement)

| | NEAT (évolution) | Gradient descent (local) |
|---|---|---|
| Optimise | topologie **et** poids | poids uniquement |
| Exploration | globale, échappe aux optima locaux | locale, converge vite |
| Besoin | juste une fitness (boîte noire) | une **loss différentiable** |

En contrôle, la fitness (distance parcourue) **n'est pas différentiable** → le GD n'a
pas de gradient naturel. On lui en fabrique un via **l'imitation de l'élite** :
loss = MSE entre les actions de l'agent et celles des champions, sur les mêmes états.
C'est différentiable, stable, et pédagogiquement clair (« la population apprend de ses
meilleurs de son vivant »).

---

## 2. Les régimes d'hybridation (switchables)

| Mode | GD pendant la vie ? | Poids transmis aux enfants | Effet attendu |
|---|---|---|---|
| **evolution_only** | non | poids de naissance | baseline neuroévolution pure |
| **gradient_only** | oui (tous) | pas de reproduction | baseline GD pur (topologie figée) |
| **write_back** (Lamarckien) | oui | **poids appris** (réinjectés au génome) | convergence rapide, progrès visible vite |
| **evaluate_only** (Baldwinien) | oui | poids de **naissance** (appris jetés) | sélectionne les topologies *entraînables* |
| **confrontation** | camp GD seulement | NEAT : naissance · GD : pas de reproduction | duel direct NEAT vs GD |

### Mode confrontation (NEAT vs GD, avec ratio)

La population est **scindée par `gd_ratio`** en deux camps étanches jouant dans le
même monde (mêmes tuyaux) :

- **camp NEAT** : évolution pure (sélection, croisement, mutation, spéciation),
  reproduction *uniquement intra-camp* ;
- **camp GD** : topologies **figées**, amélioration *uniquement* par descente de
  gradient (imitation), poids persistés de génération en génération.

Le champion d'une génération est donc **100 % NEAT ou 100 % GD**, jamais un
mélange — c'est ce qui rend les deux approches directement comparables.
`gd_teacher_scope` règle la pureté du duel : `camp` (le camp GD n'imite que ses
propres champions) ou `global` (il peut distiller les découvertes de NEAT).
L'UI rend le duel explicite : oiseaux colorés par camp, courbes max/moy par camp,
badges dans le classement, scoreboard (générations remportées, leader) sous la
barre d'outils.

- `write_back` : après les steps de GD, on écrit les poids optimisés dans le génome,
  on note la fitness avec, et la reproduction part du génome appris.
- `evaluate_only` : on clone le génome, on fait le GD sur le clone, on note la fitness
  avec le clone *appris*, mais la reproduction repart du génome **d'origine**.

---

## 3. Domaine : le Flappy-like

### Agent (entrées / sortie du réseau)
Entrées normalisées (~[-1, 1]), **chaque capteur activable depuis le front** (ça change
la taille de la couche d'entrée → un des leviers de « taille du réseau ») :
1. `Δy` — distance verticale au centre du prochain trou
2. `Δx` — distance horizontale au prochain tuyau
3. `vy` — vitesse verticale de l'oiseau
4. `Δy2` — (optionnel) distance verticale au trou *suivant*
5. `y` — (optionnel) position absolue de l'oiseau
6. (biais constant = 1.0, toujours présent)

Sortie : 1 neurone sigmoïde → **saute si > 0.5**.

### Physique (paramétrable)
- gravité constante, impulsion vers le haut au saut
- tuyaux défilent vers la gauche, trou à hauteur aléatoire
- **mort** = collision (tuyau ou bords)
- **fitness** = temps survécu + bonus par tuyau franchi

### Boucle d'évaluation
Toute la population joue **en parallèle** dans le même monde (mêmes tuyaux → comparaison
équitable). Les morts disparaissent ; la génération s'arrête quand tous sont morts ou
qu'un cap de temps est atteint.

---

## 4. Le moteur NEAT

### Génome
- **NodeGene** : `id`, `type` ∈ {input, hidden, output}, `activation`
- **ConnectionGene** : `in_node`, `out_node`, `weight`, `enabled`, `innovation`
- **InnovationTracker** global : attribue un numéro d'innovation unique par mutation
  structurelle (clé : (in, out)) pour aligner les génomes lors du crossover.

### Mutations
- perturber un poids (gaussien, σ paramétrable) ou le remplacer
- **add connection** : relie deux nœuds non connectés
- **add node** : coupe une connexion existante, insère un nœud au milieu
- (dés)activer une connexion

### Crossover
- aligner les gènes par numéro d'innovation
- gènes correspondants : hérités au hasard d'un parent
- gènes disjoints/excédentaires : pris chez le parent **le plus apte**

### Spéciation (protège l'innovation)
- distance de compatibilité : `δ = c1·E/N + c2·D/N + c3·W̄`
  (E = excédentaires, D = disjoints, W̄ = écart moyen de poids)
- regroupement en espèces sous un seuil `δ_t`
- **fitness sharing** intra-espèce ; allocation des descendants ∝ fitness ajustée
- élitisme par espèce ; reproduction par tournoi/roulette intra-espèce

---

## 5. Le gradient descent local (imitation)

### Réseau différentiable sur topologie arbitraire
NEAT produit des graphes quelconques → pas de couches denses standard. On implémente
un **mini-autograd maison** (numpy) :
- **forward** : tri topologique des nœuds, activations mises en cache
- **backward** : parcours inverse, dérivées des activations (sigmoïde/tanh), gradients
  accumulés sur chaque poids de connexion
- mise à jour : SGD simple (`w -= lr · ∂L/∂w`), `lr` et nb de steps paramétrables

### Le signal d'imitation
- **Professeur** = top-K agents de la génération précédente (K paramétrable)
- pendant que le professeur joue, on enregistre un **replay buffer** `(état, action)`
- chaque apprenant fait quelques steps de GD : `loss = MSE(sortie_apprenant(état),
  action_professeur(état))` sur un batch échantillonné du buffer
- en `evolution_only` : on saute entièrement cette phase

---

## 6. Architecture backend (FastAPI + numpy)

```
backend/
  config.py              # hyperparamètres & valeurs par défaut
  neat/
    genome.py            # NodeGene, ConnectionGene, Genome, InnovationTracker
    mutations.py         # add_connection, add_node, perturb_weights...
    crossover.py         # alignement par innovation, héritage
    speciation.py        # distance, espèces, fitness sharing
    population.py        # Population: étape de génération complète
  nn/
    network.py           # construit le réseau depuis un génome
    autograd.py          # forward (topo) + backward (gradients) maison
  learning/
    imitation.py         # replay buffer prof + steps de GD apprenant
  sim/
    flappy.py            # environnement, physique, fitness (N agents //)
  engine/
    runner.py            # orchestre 1 génération: éval (+GD optionnel) → évolue
    snapshots.py         # sérialise l'état pour le stream
  api/
    server.py            # FastAPI + WebSocket (config, contrôle, stream, select)
    schema.py            # modèles Pydantic des params + GET /config/schema
  tests/
    test_genome.py, test_crossover.py, test_autograd.py, test_speciation.py
  cli.py                 # run headless (sans front) pour valider le moteur
```

### Tout est paramétrable depuis le front

Le back ne code aucun hyperparamètre en dur : `config.py` ne définit que des **valeurs
par défaut**, et chaque champ est **surchargeable via le message `config`** du WebSocket.
Un schéma Pydantic valide/borne les valeurs reçues (garde-fous : popSize ≤ max, taux ∈
[0,1], etc.). Le front récupère ce schéma (endpoint `GET /config/schema`) pour générer
ses contrôles automatiquement et afficher min/max/défaut.

Paramètres exposés, regroupés :

- **Population & simulation** : `popSize`, `simSpeed`, `seed`, `maxTicksPerGen`,
  `streamMode` (`watch` | `fast`).
- **Taille du réseau** : `activeSensors` (liste → taille couche d'entrée),
  `initialHidden` (nb de nœuds cachés au départ, 0 = topologie minimale NEAT),
  `maxNodes` / `maxConnections` (plafonds de complexité), `activation` (sigmoid/tanh/relu).
- **NEAT** : `addConnectionRate`, `addNodeRate`, `weightPerturbRate`, `weightReplaceRate`,
  `weightSigma`, `toggleEnableRate`, `compatThreshold` (`δ_t`), coeffs `c1`,`c2`,`c3`,
  `elitismPerSpecies`, `survivalThreshold`, `targetSpecies` (option : `δ_t` auto-ajusté).
- **Hybridation / GD** : `mode` (`evolution_only`|`gradient_only`|`write_back`|
  `evaluate_only`|`confrontation`), `gdSteps`, `gdLr`, `teacherK`, `gdBatchSize`.
- **Confrontation** : `gdRatio` (fraction de la population dans le camp GD,
  structurel → appliqué au reset), `gdTeacherScope` (`camp`|`global`).

Les changements de params **structurels** (popSize, sensors, plafonds) ne s'appliquent
qu'au `reset` suivant ; les params « doux » (taux de mutation, lr, vitesse, mode) sont
applicables **à chaud** entre deux générations.

### Protocole WebSocket

**Client → serveur**
- `{type:"config", patch:{...}}` — surcharge partielle des paramètres ci-dessus
- `{type:"control", action:"play"|"pause"|"step"|"reset"}`
- `{type:"select", birdId}` — choisit l'oiseau dont on veut voir/suivre le réseau
  (par défaut : le meilleur courant)

**Serveur → client** (granularités séparées)
- `{type:"frame", gen, tick, aliveCount, birds:[{id,x,y,vy,alive,fitness,species}],
     pipes:[{x,gapY,gapH}], selectedActivations:{nodeId: value}}`
  → haute fréquence, pour le rendu live du jeu (throttlé ~30–60 fps). `selectedActivations`
  = activations *en direct* des neurones de l'oiseau sélectionné (pour illuminer son réseau).
- `{type:"generation", gen, fitnessMax, fitnessMean, species, complexity,
     bestGenome:{nodes, connections}, leaderboard:[{birdId, fitness}]}`
  → une fois par génération : courbes, topologie du best, classement cliquable.
- `{type:"genome", birdId, genome:{nodes, connections}}`
  → réponse à un `select` : le réseau complet de l'oiseau demandé.

**Deux vitesses de fonctionnement**
- *mode « watch »* : stream les frames de la génération courante (on regarde jouer)
- *mode « fast »* : saute le streaming de frames, n'envoie que les résumés de génération
  (évolution rapide, on regarde surtout les courbes)

---

## 7. Architecture frontend (Vite + React + TS)

```
frontend/
  src/
    hooks/useWebSocket.ts      # connexion + dispatch des messages
    store.ts                   # état global (zustand), inclut selectedBirdId
    api/configSchema.ts        # récupère GET /config/schema → génère les contrôles
    components/
      GameCanvas.tsx           # rendu oiseaux + tuyaux (Canvas 2D), clic = sélection
      NetworkGraph.tsx         # topologie de l'oiseau sélectionné (d3-force)
      FitnessChart.tsx         # courbes max/moy, espèces, complexité (recharts)
      Leaderboard.tsx          # classement des oiseaux, clic = sélection
      ControlPanel.tsx         # contrôles auto-générés depuis le schéma + play/pause/step
    App.tsx                    # layout
```

### Sélection d'un oiseau
- **Clic sur un oiseau** dans `GameCanvas` (ou sur une ligne du `Leaderboard`) →
  envoie `{type:"select", birdId}` et met à jour `selectedBirdId` dans le store.
- `NetworkGraph` affiche alors **le réseau de cet oiseau précis** (pas seulement le best),
  et les `selectedActivations` du flux `frame` **illuminent ses neurones en temps réel**
  pendant qu'il joue (on voit le réseau « penser »).
- L'oiseau sélectionné est **mis en surbrillance** dans le canvas (halo / couleur).
- Sélection par défaut = meilleur oiseau courant.

### Layout (panneaux synchronisés)
```
┌──────────────────────────┬───────────────────────────┐
│  JEU (Canvas)            │  RÉSEAU de l'oiseau choisi │
│  oiseaux + tuyaux        │  graphe d3-force, neurones │
│  oiseau sélectionné = ★  │  illuminés en direct       │
├──────────────────────────┼───────────────────────────┤
│  COURBES fitness/espèces │  LEADERBOARD (cliquable)   │
│  /complexité par gén.    │  top oiseaux + fitness     │
├──────────────────────────┴───────────────────────────┤
│  CONTRÔLES (auto-générés depuis le schéma) :          │
│  mode · popSize · capteurs actifs · maxNodes ·        │
│  taux mutation NEAT · steps/lr GD · vitesse · seed ·  │
│  play/pause/step/reset                                │
└───────────────────────────────────────────────────────┘
```
- **NetworkGraph (d3-force)** : simulation de forces (nœuds = particules, liens =
  ressorts) → disposition organique qui se réorganise quand la topologie change.
  Nœuds colorés par type (entrée/caché/sortie) ; halo d'intensité = activation live ;
  épaisseur/couleur des arêtes = magnitude/signe du poids.
- **ControlPanel** : généré dynamiquement à partir de `GET /config/schema` (labels,
  min/max/défaut), donc tout nouveau paramètre back apparaît sans toucher au front.
- **FitnessChart** : peut superposer les runs des 3 modes pour comparer (payoff pédago).

---

## 8. Hyperparamètres par défaut (point de départ)

| Param | Valeur |
|---|---|
| taille population | 100–150 |
| capteurs actifs / sortie | 3 (+biais) / 1 |
| nœuds cachés initiaux | 0 (topologie minimale NEAT) |
| plafonds | maxNodes 30, maxConnections 100 |
| seuil compat. `δ_t` | 3.0 (c1=1, c2=1, c3=0.4) |
| add connection | 0.05 |
| add node | 0.03 |
| perturbation poids | 0.8 (σ=0.5), remplacement 0.1 |
| GD : lr / steps | 0.05 / 5–10 par agent par génération |
| professeur | top-3 de la génération précédente |

> Tous ces chiffres ne sont que des **défauts** : surchargés à chaud depuis le front via
> le message `config`, validés/bornés par le schéma Pydantic exposé sur `GET /config/schema`.

---

## 9. Plan de validation

1. **Tests unitaires** : mutations, crossover (alignement innovation), distance de
   compatibilité, gradients de l'autograd (vérif numérique par différences finies).
2. **Headless (cli.py)** : `evolution_only` doit résoudre Flappy en quelques dizaines
   de générations.
3. **Comparaison** : activer `write_back` → convergence attendue plus rapide (moins de
   générations pour atteindre un seuil de fitness). C'est *la* démonstration cible.
4. Brancher le front seulement une fois le moteur validé en CLI.

---

## 10. Ordre de construction (phases)

- **Phase 0** — scaffold repo (back + front), `config.py`, dépendances.
- **Phase 1** — moteur NEAT (génome, forward, mutations, crossover, spéciation) + tests.
- **Phase 2** — env Flappy + runner headless ; `evolution_only` résout le jeu (CLI).
- **Phase 3** — autograd + imitation + modes `write_back` / `evaluate_only` ; compare headless.
- **Phase 4** — FastAPI + WebSocket (stream frames + générations, contrôles).
- **Phase 5** — front React (3 panneaux + contrôles).
- **Phase 6** — polish : presets, mode comparaison des 3 régimes, sauvegarde de runs.

---

## 11. Points de vigilance

- **Coût** : GD × population × générations chiffre vite → réseaux minuscules (≤ quelques
  dizaines de neurones), largement suffisant pour Flappy et garde la topologie lisible.
- **Diversité** : l'imitation peut faire collapser la diversité (tout le monde copie le
  même champion) → c'est *visible* à l'écran, donc on en fait un point pédagogique.
- **Throttling du stream** : ne pas inonder le front ; downsampler les frames, séparer
  nettement flux « frame » (rapide) et « generation » (lent).
- **Déterminisme** : seed configurable pour reproduire un run (utile pour comparer les
  modes sur les mêmes tuyaux).
