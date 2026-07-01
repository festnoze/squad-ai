# RFC v2 — Pipeline PO multi-étapes, révisé pour le développement agentique

> Révision de `RFC-po-pipeline.md` après critique. Les changements structurants :
> (1) la **complexité devient un champ de premier ordre** estimé en S1, challengé,
> et qui pilote l'effort des étapes suivantes ; (2) une **arête de retour S2→S1**
> (`resize`) : la complexité découverte en rédigeant la spec re-façonne la
> structure AVANT le code ; (3) **plus de boucle refine par nœud** — validation
> déterministe + auto-réparation par nœud, puis UN critic transversal par étape
> (le seul à voir les problèmes inter-nœuds) ; (4) l'unité de fan-out est la
> **story (avec ses tâches)**, pas le nœud ; (5) une **boucle d'évolution
> mesurée** : les échecs de build (splits, attempts) recalibrent le PO — c'est ça,
> le « PO évolutif ».

---

## 1. Principes de conception (les leçons de la v1)

1. **Estimer la complexité, pas la constater.** `file_globs` déclarés au plan
   (sur un repo vide en itération 1) sont une fiction que le check « ≤ budget »
   valide sans la fiabiliser : le LLM écrira 3 globs larges pour passer. La
   complexité est un **jugement à produire** (`complexity`, `rationale`,
   `estimated_files`), à challenger par le critic, et à **recaler sur le réel**
   (globs vérifiés contre l'arbre de fichiers dès l'itération 2 ; leçons de
   sizing issues des splits passés).
2. **La structure n'est pas figeable avant la spec.** C'est en rédigeant les
   critères qu'on découvre qu'un nœud est deux fois plus gros que son titre.
   Le pipeline doit avoir une arête de retour bon marché (verdict `resize` par
   story, appliqué localement), pas un pipeline strictement feed-forward.
3. **Un critic par nœud ne voit pas les défauts qui comptent.** Chevauchement de
   périmètres entre deux stories, conventions d'erreurs contradictoires, story
   d'intégration manquante : ce sont des défauts **inter-nœuds**. Un critic
   par nœud est structurellement aveugle à tout ça — et multiplie les appels.
   → validation **déterministe** par nœud, critique **transversale** par étape.
4. **Le déterministe d'abord, le LLM pour le non-vérifiable.** Le premier mode
   de panne d'un pipeline JSON multi-étapes est le contrat inter-étapes (ids qui
   dérivent, AC orphelins, JSON mal formé). Schéma pydantic + intégrité
   référentielle + 1 retry d'auto-réparation par nœud coûtent ~0 et attrapent
   plus que 2 tours de critic.
5. **Un seul cerveau de découpe.** Les règles de granularité (budget fichiers,
   une responsabilité, politique TS) vivent dans UN fragment de prompt partagé
   par `po-structure`, son critic, et `decompose_finer` (réactif). Sinon la
   notion de « bonne taille » du système fourche entre proactif et réactif.
6. **Évoluer = mesurer.** Sans métrique aval (splits par plan, attempts moyens,
   tâches hors budget découvertes au runtime), impossible de savoir si le
   pipeline produit de meilleurs plans que le mono-passe. Ces signaux existent
   déjà dans l'état — il faut les brancher.

## 2. Le pipeline révisé

```
brief ──▶ S1 Structure+Complexité ──▶ S2 Spec (fan-out par STORY, //) ──┐
          squelette + complexity      desc + AC taxonomisés + resize    │
          checks DÉTERMINISTES        validation schéma + auto-repair   │
          1 critic structure          ┌─────────────────────────────────┘
          leçons de sizing            ▼
                              barrière RESIZE (déterministe, 1 tour borné)
                              split/merge locaux via le cerveau commun
                                      ▼
                              1 critic TRANSVERSAL (toutes les specs)
                              re-make ciblé des seuls nœuds flaggés
                                      ▼
                    S3 Gherkin (fan-out par story, //, single-shot
                    + validation déterministe ; critic LLM réservé
                    aux stories `complex`) ──▶ merge ──▶ parse existant
```

### S1 — Structure + Complexité (séquentiel)

- **Maker** `po-structure` : squelette (epics, US/TS, tâches, `depends_on`,
  `priority`, `ui`, `stream`) + **par nœud feuille** :
  - `complexity ∈ trivial|standard|complex` + `rationale` (une phrase) ;
  - `estimated_files` (entier) ; `file_globs` exigés **seulement si le repo
    existe** (itération ≥ 2), sinon `area` indicative (ex. "domaine/persistance").
- **Prompt enrichi** : fragment de découpe commun (§5) + **leçons de sizing**
  (§6 : « à l'itération N-1, les tâches touchant X ont dû être re-découpées »).
- **Validation DÉTERMINISTE à chaque tour** (bloque l'acceptation) :
  - schéma pydantic du squelette (le nouveau : chaque étape a son schéma) ;
  - DAG acyclique (`detect_cycle`) + deps non orphelines (`validate`) ;
  - `estimated_files ≤ task_file_budget` par feuille ; `complex` sans découpe
    en tâches/TS → refus motivé ;
  - itération ≥ 2 : `file_globs` confrontés à l'arbre réel — glob qui ne matche
    rien = warning injecté, glob trop large (`**` racine) = refus ;
  - heuristique fourre-tout (multi-responsabilités dans un titre, trop de
    feuilles sous une US).
- **Critique LLM** : UN critic structure (INVEST, granularité, TS bien posées,
  parallélisme), boucle bornée par `refine_max_rounds` — mais **pas de judge
  d'ouverture** : le judge-first de `arefine` coûte un appel même quand tout va
  bien ; pour les étapes du pipeline on passe critic-d'abord (critique vide =
  accepté). Un échec d'appel critic est distingué de « critic satisfait »
  (aujourd'hui `refine.py` confond les deux → dégradation silencieuse).

### S2 — Spec (fan-out **par story**, parallèle)

- **Unité de fan-out = la story avec ses tâches** (pas « par nœud ») : une
  passe rédige description + `acceptance_criteria[{id,text,kind}]` de la story
  ET les mini-specs de ses tâches. Cohérence US↔tâches **par construction**,
  ~3× moins d'appels qu'un fan-out par nœud.
- **Sortie additionnelle** : `resize: {verdict: ok|split|merge, proposal}` —
  le rédacteur qui découvre que la story est trop grosse le DIT au lieu de
  bourrer 12 critères.
- **Par story, déterministe** : schéma pydantic + intégrité référentielle
  (ids de story/tâches ∈ squelette, AC ids uniques, chaque `kind` valide,
  couverture minimale happy+error présente) → 1 retry d'auto-réparation
  (re-prompt avec l'erreur de validation). **Pas de boucle refine par story.**
- **Barrière resize (déterministe, bornée à 1 tour)** : collecte des verdicts ;
  `split` appliqué via le **cerveau commun** (même mécanique/prompt que
  `decompose_finer`, mode proactif → extraction TS si multi-tâches, cf. RFC
  technical-stories) ; `merge` appliqué si 2 stories `trivial` adjacentes le
  demandent. Les nœuds issus du resize repassent une fois en S2. Pas de 2e tour.
- **UN critic transversal** : reçoit TOUTES les specs (compact : titres + AC) ;
  cherche exclusivement l'inter-nœuds — chevauchements, contradictions,
  conventions divergentes, trous de complétude, story d'intégration manquante.
  Sortie : liste de nœuds flaggés + motif → **re-make ciblé** de ces seuls
  nœuds (1 tour). Coût : N makers + 1 critic + k re-makes, contre
  N×(judge+critic+maker+judge) en v1.

### S3 — Gherkin (fan-out par story, parallèle)

- **Maker** `po-gherkin` : single-shot par story fonctionnelle (les TS n'ont
  pas de Gherkin fonctionnel — contrat seulement, cf. RFC technical-stories).
- **Validation déterministe** : parse Gherkin (structure Feature/Scenario,
  mots-clés), **alignement 1-pour-1 scénario ↔ AC id** (tag `@AC-x` requis),
  détection regex de steps UI/réseau interdits (« je clique », URL http) pour
  les stories non-`ui` → 1 retry d'auto-réparation.
- **Critic LLM réservé aux stories `complex`** (le champ S1 pilote l'effort) :
  exécutabilité pytest-bdd réelle, pertinence des scénarios. Les stories
  `trivial|standard` s'arrêtent à la validation déterministe.

### Merge & dégradation (sémantique explicite)

- Story dont S2 a échoué (après retry) : conserve le squelette, marquée
  `spec_incomplete` — **renvoyée en mono-passe** (le `po_plan` legacy sur ce
  seul nœud) plutôt que livrée sans critères.
- Story dont S3 a échoué : garde ses AC, `gherkin` de repli **dérivé
  mécaniquement des AC** (un scénario squelette par critère) — jamais vide,
  le QA aval a toujours une base.
- Une exception d'étape n'abandonne jamais le plan : le meilleur artefact
  continue (inchangé v1), mais chaque dégradation est **loggée + comptée** (§6).

## 3. Gating simplifié

`AUTOSPEC_PO_PIPELINE ∈ off (défaut) | on`. **Suppression du mode `auto` à
heuristiques de brief** (longueur en caractères ≈ proxy médiocre) :

- `on` → **S1 tourne toujours** (1-2 appels, c'est le levier principal).
  Ensuite, décision **déterministe post-S1 sur la taille mesurée du squelette** :
  - `< K` feuilles (défaut 4) → S2+S3 **fusionnés en une passe par story**
    (petit projet : 1 appel/story, pas de critic transversal) ;
  - `≥ K` → pipeline complet.
- `AUTOSPEC_PO_PIPELINE_GHERKIN=0` conservé (couper S3).
- Le pipeline actif remplace `_arefine_plan` (inchangé v1) — mais le critic
  transversal S2 **reprend la responsabilité TS** de l'addendum technical-stories
  (recommander l'extraction en TS des unités trop grosses), qui sinon disparaît
  avec la revue whole-plan.

## 4. Anticipation de la complexité — le fil rouge

| Moment | Mécanisme | Ce que ça corrige |
|---|---|---|
| S1 | `complexity` + `rationale` + `estimated_files` estimés, challengés par checks + critic | La taille n'est plus implicite dans un titre |
| S1 | Leçons de sizing injectées (splits passés, attempts) | Le PO se recalibre sur les échecs réels (§6) |
| S2 | Verdict `resize` par story + barrière d'application | La complexité découverte en rédigeant re-façonne la structure avant le code |
| S2/S3 | `complexity` pilote l'effort (critic réservé aux `complex`) | Budget de qualité dépensé là où c'est dur |
| Runtime | Split-on-failure → TS (RFC technical-stories, inchangé) | Filet réactif quand l'anticipation a raté |
| Runtime | Chaque split/attempt est un **signal de calibration** persisté | La boucle se ferme : l'échec d'aujourd'hui dimensionne le plan de demain |

## 5. Cerveau de découpe unique

Un fragment de prompt partagé `SIZING_RULES` (dans `prompts.py`) : budget
fichiers, « une responsabilité par feuille », politique TS (quand extraire),
règle des zones disjointes. Consommé par : `po_structure`, `STRUCTURE_CRITERIA`,
le critic transversal S2, et `decompose_finer`. Une seule définition de la
« bonne taille » pour le proactif ET le réactif.

## 6. Boucle d'évolution (le « PO évolutif », mesuré)

- **Métriques par plan**, persistées dans `ProjectState` : nb de splits
  réactifs, attempts moyens par tâche, nb de tâches ayant dépassé le budget
  fichiers au runtime (diff réel des worktrees, déjà observable), nb de
  dégradations d'étapes.
- **Sizing lessons** : chaque split réactif émet une leçon structurée
  (« {zone/type de tâche} sous-dimensionnée → re-découpée en N ») stockée avec
  les leçons E7 et **injectée dans S1** à l'itération suivante.
- **Éval A/B avant activation par défaut** : 2-3 briefs de référence en
  scripted + 1 réel, mono-passe vs pipeline, comparés sur les métriques
  ci-dessus. Le pipeline ne passe `on` par défaut que s'il réduit les splits
  réactifs / attempts. Sans ça, aucune preuve que la complexité ajoutée paie.

## 7. Impact code

| Zone | Changement |
|---|---|
| `models.py` | `AcceptanceCriterion.kind` ; `Task.complexity/estimated_files` ; `UserStory.complexity` ; compteurs de calibration dans `ProjectState` (tous optionnels ⇒ legacy inchangé) |
| `agents/prompts.py` | `SIZING_RULES` partagé ; `po_structure`, `po_spec_story` (story+tâches+resize), `po_gherkin` ; `STRUCTURE_CRITERIA`, `CROSS_SPEC_CRITERIA` ; `decompose_finer` re-branché sur `SIZING_RULES` |
| `agents/personas.py` | `po-structure`, `po-spec`, `po-gherkin` |
| `orchestrator/plan_pipeline.py` (nouveau) | schémas pydantic des artefacts d'étapes ; validation + auto-repair ; S1→resize→critic transversal→S3 ; merge + dégradation. (Nouveau module : `pipeline.py` fait déjà 5200 lignes.) |
| `orchestrator/refine.py` | variante critic-d'abord (pas de judge d'ouverture) + distinction « critic en échec » vs « critic satisfait » |
| `orchestrator/pipeline.py` | branchement dans `_aplan_phase` derrière le gating ; émission des signaux de calibration depuis `_amaybe_split_on_failure` |
| `config.py` | `AUTOSPEC_PO_PIPELINE` (off/on), `AUTOSPEC_PO_PIPELINE_MIN_LEAVES` (K), `AUTOSPEC_PO_PIPELINE_GHERKIN` |
| `agents/scripted.py` | réponses S1/S2 (avec un cas `resize:split`)/S3 |
| Frontend | (option) badge complexité + `kind` des critères + compteur de calibration |

## 8. Plan de livraison (revu)

1. **Fondation contrats** : schémas pydantic des artefacts S1/S2/S3 +
   validation/auto-repair génériques + variante critic-d'abord de `refine` +
   tests. *(C'est la fondation qui rend chaque étape testable en isolation.)*
2. **S1** : `SIZING_RULES` + persona/prompt/criteria + checks déterministes
   (dont vérif des globs sur repo existant) + injection des leçons + tests.
3. **S2** : fan-out par story + resize barrier + critic transversal + re-make
   ciblé + tests (dont : un `resize:split` produit une TS via le cerveau commun).
4. **S3** : single-shot + validation gherkin/alignement AC + gating par
   complexité + gherkin de repli + tests.
5. **Intégration** : gating post-S1, merge + dégradation, scripted, branchement
   `_aplan_phase`, mode fusionné petit-projet + tests bout-en-bout.
6. **Boucle d'évolution** : métriques de calibration + sizing lessons +
   éval A/B sur briefs de référence. *(Critère d'activation par défaut.)*
7. **Frontend + docs** (option) : badges, FEATURES, mémoire.

## 9. Ce qui est volontairement abandonné de la v1

- Le mode `auto` à seuils de longueur de brief (remplacé par la décision
  post-S1 sur taille mesurée).
- La boucle maker→critic→judge **par nœud** en S2/S3 (remplacée par
  déterministe par nœud + critic transversal par étape).
- Les `file_globs` obligatoires en itération 1 (remplacés par
  `estimated_files` + `area` ; globs réels exigés dès que le repo existe).
- Le panel de critics S2 « option » (le critic transversal + le gating par
  complexité couvrent le besoin à coût borné).
