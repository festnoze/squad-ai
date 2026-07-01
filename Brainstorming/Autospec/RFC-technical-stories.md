# RFC — Technical Stories (TS) : décomposition récursive sur échec

> **Décisions actées** : (1) nœud **récursif uniforme** ; (2) déclenchement **réactif
> uniquement** (la TS naît du split-on-failure) ; (3) **spec avant code**.
> Objectif : décrire des features complexes finement décomposables, garantir un
> **parallélisme massif** et qu'**aucune tâche feuille n'excède ~3 fichiers /
> complexité « LLM moyen »**.

---

> **Addendum (2026-06-30)** — les TS sont désormais créées **proactivement** aussi :
> le **PO** peut émettre des Technical Stories directement dans le plan
> (`technical:true` + `contract`, groupant des tâches ≤ budget fichiers), et le
> **critic** de la revue de plan (`AUTOSPEC_REVIEW_PLAN`) recommande l'extraction en
> TS des unités trop grosses ; `po_revise` applique. Même structure de TS, deux
> moteurs (plan **proactif** + échec **réactif**).

## 1. Concept

Une **Technical Story (TS)** est un **conteneur de travail technique** : pas de valeur
fonctionnelle haut niveau, pas de Gherkin fonctionnel, mais un **contrat technique**
et un **groupe de tâches** (ou d'autres TS via le DAG). Elle est **affichée au même
niveau qu'une US** et sert généralement de **dépendance** d'une tâche/US.

Elle naît **quand une tâche échoue** (tests rouges, tentatives épuisées) **et qu'elle
est trop grosse** : au lieu de l'aplatir en tâches sœurs anonymes (P6 actuel), on la
**promeut en une TS nommée, adressable et affichée**, contenant des sous-tâches plus
fines.

## 2. Modèle — réutilisation maximale (pas de type bricolé)

**Décision : une TS EST une `UserStory` avec `technical=True`** (+ un champ `contract`,
sans `gherkin` fonctionnel). Raisons :

- elle vit dans le **même `state.stories`** → apparaît sur le board, est adressable
  (rebuild/split/diff), porte déjà `tasks`, `depends_on`, `split_depth`, `stream` ;
- **`build_work_graph` la gère déjà** : « dépendre d'une story décomposée = dépendre
  de TOUTES ses tâches » ([streams.py](backend/autospec/orchestrator/streams.py)). La
  résolution récursive des dépendances est donc **gratuite**.

```python
class UserStory(BaseModel):
    ...
    technical: bool = False     # True ⇒ Technical Story (pas de valeur fonctionnelle)
    contract: str = ""          # contrat technique (remplace le gherkin fonctionnel)
    parent_id: str = ""         # la US/tâche d'origine dont cette TS a été extraite (traçabilité/board)
```

`kind` logique = `epic | story | technical-story | task`, mais **réifié** par
`epic`/`UserStory(technical=…)`/`Task` existants — **aucune nouvelle entité racine**.

### Récursivité « uniforme » SANS nesting physique

Les TS sont des **pairs à plat** dans `state.stories` ; la **profondeur vit dans le
DAG**, pas dans un arbre de conteneurs imbriqués. Une tâche d'une TS qui échoue crée
**une autre TS de plus haut niveau**, et l'arête `depends_on` relie les deux →
**profondeur arbitraire**. C'est **équivalent en pouvoir d'expression** au nesting
TS-dans-TS, mais sans réécrire le work-graph ni migrer le stockage. *(Le nesting
physique est rejeté : même puissance, coût bien supérieur.)*

## 3. Invariante de finesse (le cœur de la valeur)

**Chaque tâche feuille déclare ≤ `AUTOSPEC_TASK_FILE_BUDGET` fichiers** (défaut **3**)
dans ses `file_globs` (déjà collectés en P4) et un périmètre étroit. Le split produit
des sous-tâches qui **respectent ce budget** ; une sous-tâche encore au-dessus est
elle-même re-décomposable (jusqu'à `split_depth` / budget de profondeur).

→ C'est **mesurable** (compter les globs), donc la garantie « pas de tâche trop grosse »
est **vérifiable**, pas déclarative. Et beaucoup de petites feuilles disjointes ⇒
**parallélisme massif** (le garde-fou d'indépendance P4 reste actif).

## 4. Flux réactif (le seul déclencheur retenu)

Branché sur la branche « rouge-épuisé » déjà existante (`_abuild_work_item`), en
remplacement/extension de `_split_task` :

1. **Trigger** : tâche `T` (dans le conteneur `C` = US ou TS) FAILED après ses
   tentatives **et** `split_depth(T) < AUTOSPEC_SPLIT_MAX_DEPTH`.
2. **Architecte** (`decompose_finer`, déjà là) : produit 2–6 sous-tâches **≤ budget
   fichiers**, avec `file_globs` disjoints + dépendances internes.
3. **Promotion en TS** : créer `TS = UserStory(technical=True, parent_id=T.id,
   epic_id=C.epic_id, title=T.title, contract=<de T.description + l'erreur>,
   tasks=<sous-tâches>, split_depth=T.split_depth+1)`.
4. **Recâblage du DAG** (cycle-safe, on casse défensivement comme aujourd'hui) :
   - `TS.depends_on = T.depends_on` (amont hérité) ;
   - tout nœud qui dépendait de `T` dépend maintenant des **tâches feuilles de la TS** ;
   - retirer `T` de `C.tasks` et ajouter la TS comme **dépendance de `C`**
     (`C.depends_on += TS.tasks`), pour que `C` n'soit pas « done » avant la TS.
5. Le scheduler reprend : les tâches de la TS (TODO) sont ordonnancées comme les autres.

### Point délicat #1 — statut effectif d'un conteneur qui a essaimé une TS
`effective_status` d'une story-avec-tâches devient : **DONE ssi (toutes ses tâches
DONE) ET (toutes ses dépendances de niveau US résolues DONE)**. Sinon une US pourrait
afficher « done » alors que la TS qu'elle a extraite n'est pas finie. *(Petite
généralisation, à tester explicitement.)*

### Point délicat #2 — tests / « done » d'une TS
Une TS n'a pas d'acceptance fonctionnelle. Elle est **verte quand toutes ses tâches
sont vertes** ; ses tâches dérivent leurs tests unitaires de leur **mini-Gherkin
technique** (déjà produit par `decompose_finer`) au lieu d'un Gherkin fonctionnel. Pas
de QA outside-in fonctionnelle sur une TS.

### Point délicat #3 — borne
`split_depth` (budget de profondeur, `AUTOSPEC_SPLIT_MAX_DEPTH`) **plus** le budget
fichiers bornent la récursion : on arrête de promouvoir des TS quand les feuilles
tiennent dans le budget ou que la profondeur max est atteinte (sinon FAILED, comme
aujourd'hui).

## 5. Board / UI

- Les TS s'affichent **au niveau des US**, sous leur Epic, avec un **badge 🔧
  Technique** et leur `contract` au lieu du Gherkin.
- Elles apparaissent comme **dépendance** (⛓) sur les cartes qui en ont besoin
  (`blockedBy` fonctionne déjà sur les ids).
- `parent_id` permet un lien « extraite de US-x / T-y » (fil d'Ariane).
- Actions par TS : ✂️ Découper plus fin, 🔄 Relancer, 📊 Diff — réutilisent les
  endpoints existants (une TS = une story).

## 6. Impact code (incrémental, faible risque)

| Zone | Changement |
|---|---|
| `models.py` | `UserStory.technical/contract/parent_id` (défauts ⇒ legacy inchangé) |
| `config.py` | `AUTOSPEC_TASK_FILE_BUDGET=3` (+ réutilise `SPLIT_MAX_DEPTH`) |
| `pipeline.py` | `_split_task` → promotion en TS (au lieu de tâches sœurs) ; `effective_status` généralisé ; le `decompose_finer` impose le budget fichiers |
| `streams.py` | rien (résolution « dépendre d'une story = ses tâches » déjà là) ; vérifier cycle-safety du recâblage |
| `prompts.py` | `decompose_finer` : exiger ≤ budget fichiers par sous-tâche |
| Frontend | rendu TS (badge 🔧 + contract), lien `parent_id` ; types/i18n |
| Tests | promotion en TS, recâblage des dépendants, `effective_status` conteneur-avec-dep, budget fichiers, profondeur bornée, board |

**Compatibilité** : `technical=False` partout par défaut ⇒ projets existants **byte-
identiques**. La feature ne s'active que quand un split se produit.

## 7. Risques & garde-fous

- **Sur-décomposition** → bornée par `split_depth` + budget fichiers ; le split ne se
  déclenche que **sur échec** (réactif).
- **Cycles** lors du recâblage → on garde la détection/casse défensive existante
  (`detect_cycle`, 3-couleurs) ; tests dédiés.
- **Explosion du board** → les TS sont repliables ; un projet sain en a peu.
- **Coût (merges/worktrees)** → plus de feuilles = plus de merges, mais P2 (rebase-
  preserve) + P4 (sérialisation par fichiers) limitent les conflits.

## 8. Plan de livraison (phases)

1. **Modèle + config** (`technical/contract/parent_id`, `TASK_FILE_BUDGET`) + tests modèle.
2. **`_split_task` → promotion TS** + recâblage + `effective_status` généralisé + tests backend (le cas todo : tâche échoue → TS créée, dépendants recâblés, US done seulement après TS).
3. **`decompose_finer`** : contrainte budget fichiers + scripted.
4. **Frontend** : rendu TS (badge/contract/parent), types, i18n, tests vitest.
5. **Doc** : FEATURES, REFACTOR_PLAN (P7), mémoire.

## 9. Décisions (tranchées pour l'implémentation)

1. **Budget fichiers** : `AUTOSPEC_TASK_FILE_BUDGET=3`, **indicatif** — communiqué à
   l'architecte comme cible (« ≤ 3 fichiers/sous-tâche »), pas un rejet runtime dur
   (trop fragile). Un dépassement est juste loggé.
2. **Statut conteneur** : **pas** de généralisation de `effective_status` (éviter le
   couplage à l'état + les risques de cycle). La **TS est une story de plein droit** →
   déjà suivie par le delivery-gate et le board. La correction d'**ordonnancement** est
   assurée par : (a) recâblage des dépendants directs de la tâche vers les feuilles de
   la TS, (b) **résolution de leaf-tasks dans `build_work_graph`** : « dépendre d'une
   story S = dépendre de ses tâches **+** des tâches de ses TS-enfants (`parent_id==S`,
   récursif) ». **Cycle-safe** : l'amont de la tâche n'est jamais recâblé.
3. **Extraction vs in-place** : on **extrait en TS uniquement si le conteneur garde ≥1
   tâche** (jamais de conteneur vide) ; sinon **fallback in-place** (P6 actuel). Une
   **US fonctionnelle** trop grosse reste découpée en **tâches** (`_split_story`, une US
   ne devient jamais une TS) ; la TS naît de l'extraction d'une **tâche**.
