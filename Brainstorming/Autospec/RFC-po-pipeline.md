# RFC — Pipeline PO multi-étapes (Structure → Spec → Gherkin)

> **Décisions actées** : (1) **3 étapes** (Structure → Spec → Gherkin), la rédaction
> et les critères fusionnés en « Spec » pour éviter la dérive ; (2) **gated par
> complexité + env** (mono-passe pour les petits projets) ; (3) **spec avant code**.
> Objectif : meilleure qualité de plan **par dimension**, en maîtrisant cost/latence
> via la réutilisation du harnais `refine`, la validation **déterministe** de la
> structure, le **fan-out parallèle** et l'arrêt-tôt.

---

## 1. Principe

Remplacer l'appel PO monolithique (`po_plan` + `_arefine_plan`) par un **pipeline de
3 étapes spécialisées**, chacune = une **boucle de raffinement** (maker → critic →
juge) réutilisant `orchestrator/refine.py`. Un **artefact partagé** (le plan JSON) est
**enrichi étape par étape** ; la structure est en plus **validée déterministiquement**.

```
brief ──▶ S1 Structure ──▶ S2 Spec (par nœud, //) ──▶ S3 Gherkin (par story, //) ──▶ plan final
          (squelette)       (+desc +critères)          (+gherkin exécutable)        └▶ parse existant
          critic + checks    critic                     critic
          DÉTERMINISTES
```

Chaque étape : maker (persona dédiée) → `refine.arefine` (critic `critic`, juge
`judge`, **critères propres à l'étape**), arrêt déterministe (seuil/cap) déjà en place.

## 2. Artefact partagé (enrichissement progressif)

- **S1 — Structure** produit le **squelette** : `epics[]`, `stories[]` (US/**TS**),
  `tasks[]` par stream, `depends_on`, `priority`, `ui`, `stream`, `file_globs`,
  `technical/contract` — **titres courts seulement**, PAS de description/critères/gherkin.
- **S2 — Spec** (fan-out par nœud) ajoute à chaque nœud : `description` complète et
  `acceptance_criteria` **taxonomisés** (chaque critère porte un `kind` ∈
  `happy|edge|error|boundary`). Couvre explicitement le chemin nominal **et** les cas
  limites/erreurs.
- **S3 — Gherkin** (fan-out par story/TS) ajoute le `gherkin` **contextuel et
  exécutable** (pytest-bdd, langage backend du projet), aligné 1-pour-1 sur les
  critères de S2.

Le **parse final** (`_aplan_phase` → `new_stories`) est **inchangé** : il consomme le
plan JSON enrichi exactement comme aujourd'hui (les nouveaux champs `kind` de critère
sont optionnels et ignorés par le parse legacy → compat totale).

## 3. Les 3 étapes en détail

### S1 — Structure (séquentiel, plus fort levier)
- **Maker** : persona `po-structure` (« découpe sans rédiger »). Prompt = brief →
  hiérarchie + dépendances + dimensionnement (≤ `TASK_FILE_BUDGET` fichiers/feuille,
  TS pour le technique/complexe).
- **Critic** : persona `critic` + `STRUCTURE_CRITERIA` (INVEST, granularité, TS bien
  posées, parallélisme, dépendances minimales).
- **Validation DÉTERMINISTE (l'edge unique)** — exécutée à chaque tour et **injectée
  dans la critique** + **bloque le juge** tant qu'il reste un problème :
  - DAG **acyclique** (`streams.detect_cycle`), dépendances **non orphelines**
    (`streams.validate`) ;
  - chaque tâche feuille déclare des `file_globs` et **≤ budget fichiers** ;
  - chevauchements de fichiers → l'indépendance (P4) injecte les `depends_on` ;
  - pas d'US « fourre-tout » (heuristique : trop de critères annoncés / multi-resp.).
  → On *prouve* la structure ; le LLM-critic ne traite que le non-vérifiable.

### S2 — Spécification (fan-out parallèle par nœud)
- **Maker** : persona `po-spec`. Entrée = un nœud du squelette + le brief + son
  contexte (epic, voisins). Sortie = `description` + `acceptance_criteria[{id,text,kind}]`.
- **Critic** : `SPEC_CRITERIA` — **complétude** (happy ET edge ET error ET boundary),
  testabilité, non-ambiguïté, alignement à la structure. *(Option : panel de critics
  à lentilles diverses pour la complétude — réservé high-value.)*
- Parallélisé sur les nœuds (sémaphore `AUTOSPEC_MAX_PARALLEL_DEVS`).

### S3 — Gherkin (fan-out parallèle par story/TS)
- **Maker** : persona `po-gherkin`. Entrée = une story + ses critères S2 + langage
  backend. Sortie = `gherkin` exécutable pytest-bdd, 1 scénario par critère clé.
- **Critic** : `GHERKIN_CRITERIA` — exécutabilité, alignement strict aux critères,
  Given/When/Then nets, pas de dépendance UI/réseau (sauf stories `ui`).
- Parallélisé par story.

## 4. Gating (complexité + env)

`AUTOSPEC_PO_PIPELINE` ∈ `off` (défaut) | `on` | `auto`.
- **off** : comportement actuel (`po_plan` + `_arefine_plan`/REVIEW_PLAN).
- **on** : toujours le pipeline 3 étapes.
- **auto** : heuristique de complexité — pipeline si l'un de : brief « long »
  (> N chars), `streams_enabled`/multi-stream, `idea_maturity == "structured"` avec
  périmètre large, ou (post-S1) **≥ K user stories / présence de TS ou d'US
  décomposées**. Sinon → mono-passe. *(S1 étant peu coûteux, on peut le lancer puis
  décider de S2/S3 selon la taille produite.)*

Quand le pipeline est actif, il **remplace** le whole-plan `_arefine_plan`
(`AUTOSPEC_REVIEW_PLAN`) : les critics par étape couvrent mieux. Granularité possible :
`AUTOSPEC_PO_PIPELINE_GHERKIN=0` pour couper l'étape la plus chère.

## 5. Maîtrise cost / latence

- **Gating complexité** → les petits projets gardent 1-2 appels.
- **Arrêt-tôt** (juge ≥ seuil) déjà dans `refine` → un critic ne tourne que si la
  qualité manque.
- **Checks déterministes** remplacent des tours de critic LLM sur S1 (gratuit, fiable).
- **Fan-out parallèle** S2/S3 → latence ≈ « 3 étapes », pas « 3 × N nœuds ».
- **Dégradation gracieuse** : une étape qui échoue (AgentError) → on garde le meilleur
  artefact en l'état et on continue (jamais de crash du plan).

## 6. Impact code

| Zone | Changement |
|---|---|
| `agents/personas.py` | personas `po-structure`, `po-spec`, `po-gherkin` |
| `agents/prompts.py` | `po_structure`, `po_spec`, `po_gherkin` + `STRUCTURE/SPEC/GHERKIN_CRITERIA` |
| `orchestrator/pipeline.py` | `_aplan_pipeline()` (S1→S2→S3, fan-out, merge) ; branché dans `_aplan_phase` derrière le gating ; validation déterministe S1 (réutilise `streams.validate`/`detect_cycle` + budget fichiers) |
| `orchestrator/refine.py` | rien (réutilisé tel quel ; `accept` callback pour bloquer S1 sur check déterministe) |
| `models.py` | `AcceptanceCriterion.kind: str = ""` (happy/edge/error/boundary ; optionnel) |
| `config.py` | `AUTOSPEC_PO_PIPELINE` (+ heuristique) |
| `agents/scripted.py` | réponses scriptées S1/S2/S3 (démo/tests) |
| Frontend | (optionnel) afficher le `kind` des critères + le score par étape ; non bloquant |

**Compat** : `AUTOSPEC_PO_PIPELINE=off` par défaut ⇒ comportement **byte-identique**.

## 7. Tests

- `test_po_pipeline.py` : S1 produit un squelette valide ; un squelette à cycle/budget
  dépassé est **rejeté** par les checks déterministes (critique injectée) ; S2 ajoute
  des critères taxonomisés (happy+edge+error) ; S3 ajoute un Gherkin aligné ; merge →
  plan parseable ; gating (off→mono-passe, on→pipeline, auto→heuristique) ; dégradation
  gracieuse si une étape lève.
- Fan-out : S2/S3 tournent en parallèle (sémaphore respectée).

## 8. Plan de livraison (phases)

1. **Modèle + config** (`AcceptanceCriterion.kind`, `AUTOSPEC_PO_PIPELINE`) + gating squelette.
2. **S1 Structure** : prompt + persona + critic + **validation déterministe** + tests.
3. **S2 Spec** : prompt + persona + critic + fan-out + taxonomie critères + tests.
4. **S3 Gherkin** : prompt + persona + critic + fan-out + tests.
5. **Merge + intégration** dans `_aplan_phase` + scripted + dégradation gracieuse.
6. **Frontend (option)** : `kind` des critères / scores par étape.
7. **Docs** : FEATURES, REFACTOR_PLAN, mémoire.

## 9. Décisions / questions ouvertes

1. **Personas distinctes vs skills** : je pars sur **personas distinctes** (form « 3
   étapes » choisie) ; on pourra exposer les prompts comme skills plus tard.
2. **Panel de critics S2** : OFF au premier jet (un seul critic) ; activable ensuite si
   la complétude des edge cases reste faible.
3. **Heuristique `auto`** : seuils exacts (longueur brief, K user stories) à caler —
   défauts proposés, ajustables par env.
