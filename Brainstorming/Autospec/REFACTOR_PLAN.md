# Autospec — Plan de refactor « zéro échec perpétuel »

> Objectif : qu'un projet simple (todo-list) **ne puisse plus** rester bloqué, et que
> le parallélisme ne s'active **que** sur des tâches dont l'indépendance est **prouvée**.
> Intègre les deux analyses de cause racine (`todo_list_2`).

---

## 1. Synthèse unifiée des causes racines

Preuve transverse : **le code généré est correct**. Sur `todo_list_2`, `uv run pytest`
→ **53 passed**, `vitest run` → **1 passed**, `tsc && vite build` → **OK**. L'échec est
**100 % orchestration** : du travail « green » est produit puis **jamais livré**.

| # | Cause racine | Preuve | Emplacement |
|---|---|---|---|
| C1 | **`STREAMS=1` global** : tout projet, même trivial, emprunte le chemin parallèle streams+worktrees+merge. | `.env` ; défaut code `False`. | [config.py:306](backend/autospec/config.py#L306), [backend/.env](backend/.env) |
| C2 | **Fausse indépendance** : `T-3-fe` et `T-4-fe` sont dans le **même** `frontend`/`file_root`, éditent tous deux `App.tsx`, mais sont planifiés **parallèles** (aucun `depends_on` entre eux). | Les 2 sont `frontend`, App.tsx reste le scaffold. | [pipeline.py:2923](backend/autospec/orchestrator/pipeline.py#L2923), [streams.py:166](backend/autospec/orchestrator/streams.py#L166) |
| C3 | **Travail « green » perdu** : le dev répond « tests verts + build OK » mais **aucun `merge work item T-3-fe/T-4-fe`** n'existe ; le worktree (avec le code) est supprimé en `finally`. | `git log` : pas de merge fe ; `App.tsx` = placeholder. | [pipeline.py:3146-3216](backend/autospec/orchestrator/pipeline.py#L3146) |
| C4 | **Fichiers volatils commités** : `autospec-state.json` / `autospec-interactions.jsonl` sont **tracés** ; `_acommit_story` fait `git add -A`. Réécrits à chaque `_sync()` → conflits/churn de merge garantis. | `git ls-files` les montre ; pas dans `.gitignore`. | [pipeline.py:2591](backend/autospec/orchestrator/pipeline.py#L2591) |
| C5 | **Retry de merge no-op** : sur conflit → `merge --abort` puis **même merge identique** sous le même verrou (rien n'a changé). | « conflit de merge inter-stream » sur `T-3-be`. | [pipeline.py:3410](backend/autospec/orchestrator/pipeline.py#L3410) |
| C6 | **Un worker plante = tout le build meurt** : `_reap_done` annule tous les autres et relance l'exception → pipeline ERROR/stop. Déclencheur observé : `claude CLI exited with 1073807364` (process tué Windows). | logs d'interactions. | [pipeline.py:2963](backend/autospec/orchestrator/pipeline.py#L2963) |
| C7 | **`node_modules` worktree fragile** : jonction `mklink /J` best-effort ; vérifs frontend en worktree échouent (`vite`/`tsc` introuvables) alors que le workspace principal build. | « node_modules vide / npm install » répétés. | [pipeline.py:4156](backend/autospec/orchestrator/pipeline.py#L4156), [4173](backend/autospec/orchestrator/pipeline.py#L4173) |
| C8 | **Récupération des orphelins incomplète** : `in_progress` resté après crash (entre « réponse dev » et « statut/merge persisté ») n'est pas remis à `todo`/`failed` par retry/resume tant qu'une pipeline mémoire existe. | `T-3-fe`/`T-4-fe` figés `in_progress`. | [pipeline.py:3498](backend/autospec/orchestrator/pipeline.py#L3498), [server.py:84](backend/autospec/api/server.py#L84) |
| C9 | **Definition of Done « tout ou rien »** + auto-spec indéfini : un Todo devient 9 US ; si US-3→9 ne finissent pas, le projet entier paraît « échoué ». | `auto_spec: True`, 9 US. | [profiles.py:90](backend/autospec/orchestrator/profiles.py#L90) |
| C10 | **`files_hint` mort** : le champ « fichiers/zones touchés » existe sur `Task` mais n'est **jamais** rempli ni lu → aucune base pour juger l'indépendance. | grep : 1 seule occurrence (la déclaration). | [models.py:255](backend/autospec/models.py#L255) |

**Chaîne causale** : C1 force le parallèle → C2 crée des tâches faussement indépendantes →
elles se marchent dessus → C5 ne résout pas le conflit, C3 perd le code, C6 tue le build,
C8 laisse des orphelins → C9 fait paraître tout le projet en échec → le retry re-emprunte
le même chemin et reproduit C2/C5/C6 à l'identique : **échec perpétuel**.

---

## 2. Principes directeurs

1. **Ne jamais perdre du travail green.** Un item vert est mergé ou conservé (jamais un worktree green supprimé sans trace).
2. **Isolation des pannes.** Une exception d'un worker → cet item FAILED, **jamais** tout le build.
3. **Paralléliser seulement l'indépendance prouvée.** Par défaut, **sérialiser par `file_root`** ; n'autoriser le parallèle que sur des tâches dont les **revendications de fichiers ne se chevauchent pas**, validé par un **juge d'indépendance**.
4. **Repo propre.** Aucun fichier de bookkeeping dans le git du projet ; commits ciblés (pas de `git add -A`).
5. **Décomposer au maximum, ordonnancer prudemment.** Plus de petites tâches = mieux, mais l'ordonnancement reste conservateur tant que l'indépendance n'est pas certifiée.
6. **Progrès partiel = succès partiel.** Une story dont les tâches sont vertes est livrée même si d'autres stories échouent (pas de « tout ou rien »).

---

## 3. Le sous-système d'indépendance (cœur de la demande)

### 3.1 Pipeline en 3 étages, avant tout build parallèle

```
US  ──▶ (A) Décomposeur          ──▶ tâches atomiques + file_globs revendiqués
        (architect, "découper au maximum")
    ──▶ (B) Analyseur déterministe ──▶ graphe de conflits (overlap de fichiers)
        (independence.py, pur)         + partition parallélisable
    ──▶ (C) Juge d'indépendance     ──▶ certifie / corrige : ajoute depends_on,
        (skill + persona, LLM)          fusionne, ou force la sérialisation
    ──▶ scheduler : ne parallélise QUE les classes certifiées disjointes
```

### 3.2 (A) Décomposeur — « découper autant que possible »
- Étend `prompts.decompose_story` : demande des **tâches atomiques** (1 responsabilité, 1 zone de fichiers), et **oblige** chaque tâche à déclarer ses `file_globs` (active `Task.files_hint`, C10).
- Heuristique backend : 1 tâche/couche (entité → repo → service → endpoint → tests), déjà l'esprit SK-2.
- Heuristique frontend : 1 tâche/**composant ou fichier** (pas « tout App.tsx »), + 1 tâche d'intégration/route qui **dépend** des composants.
- Règle dure : **deux tâches ne peuvent pas revendiquer le même fichier** sans relation `depends_on` (sinon le juge les fusionne ou les sérialise).

### 3.3 (B) Analyseur déterministe — `orchestrator/independence.py` (nouveau, pur)
Entrée : liste de tâches `(id, stream, file_globs, depends_on)`. Sortie :
- **graphe de conflits** : arête entre 2 tâches dont les globs se chevauchent (même fichier/zone) **sans** ordre `depends_on` ;
- **constraints** : `depends_on` à ajouter pour sérialiser chaque paire en conflit (ordre stable, déterministe) ;
- **partition** : classes de tâches réellement parallélisables (aucun chevauchement intra-classe) ;
- **warnings** : revendications manquantes (`file_globs` vide → traité comme « tout le `file_root` » = sérialisé par sécurité).
Fonctions pures, **100 % testables** sans LLM (voir §5). C'est le garde-fou : même si le juge LLM se trompe, l'analyseur **interdit** le parallèle sur chevauchement.

### 3.4 (C) Juge d'indépendance — skill `task-independence` + persona `independence-judge`
- **Skill** : `backend/autospec/skills/task-independence/SKILL.md` (+ entrée `skill-rules.json`).
- **Persona** : `independence-judge` dans `personas.py`.
- Reçoit les tâches **et** le verdict déterministe de l'analyseur. Mission : pour chaque paire signalée « potentiellement en conflit », trancher : `independent` / `add_dependency(a→b)` / `merge(a,b)` ; et compléter les `file_globs` lacunaires. **Sortie JSON bornée** (comme les autres agents programmatiques).
- **Le déterministe a le dernier mot sur la sûreté** : le juge peut *ajouter* des contraintes, jamais *retirer* une sérialisation imposée par un chevauchement réel non justifié.

### 3.5 Conséquence sur le scheduler
`_abuild_phase_streams` ne remplit un slot que si l'item est `is_ready` **ET** appartient à une
classe parallélisable certifiée disjointe de tous les items en vol (`running`). Par défaut
(certification absente) → **sérialisation par `stream.file_root`** (corrige C2 immédiatement).

---

## 4. Plan par phases

### P0 — Hotfix stabilité (jour 0, faible risque, débloque « tous échouent »)
- **Config** : `STREAMS=0` dans [backend/.env](backend/.env) (retour build série, chemin prouvé vert). *(C1)*
- **Repo propre** : ajouter `autospec-state.json`, `autospec-interactions.jsonl` au `.gitignore` du workspace **et** remplacer `git add -A` par un add ciblé du code. *(C4)*
- **Worker non-fatal** : dans `_reap_done`, **logger + marquer l'item FAILED**, ne plus relancer l'exception ni annuler les siblings. *(C6)*
- **Orphelins** : au `resume_build`/retry, remettre toute tâche `in_progress`/`green`/`red` **sans worker actif** → `todo`. *(C8)*
- **Acceptance P0** : relancer le brief todo-list → projet `done`, app lançable, aucun item figé.

### P1 — Sérialisation par file_root (corrige la fausse indépendance sans LLM)
- Scheduler : grouper les items par `stream` effectif ; **au plus un item en vol par `file_root`** tant que l'indépendance n'est pas certifiée. *(C2)*
- `_amerge_work_item` : sur conflit, **ne pas** retry à l'identique — **rebaser** le worktree sur HEAD à jour puis re-merger ; échec persistant → **requeue borné par `dev_max_attempts`** (la branche verte est conservée et **reprise** au passage suivant, cf. P2b ; l'injection de `depends_on` vers l'item gagnant, envisagée initialement, n'a pas été implémentée — le requeue borné + la reprise couvrent le besoin). *(C5)*
- **Acceptance** : 2 tâches frontend qui touchent `App.tsx` ne tournent jamais en parallèle ; le 2ᵉ part du HEAD contenant le 1er.

### P2 — Ne jamais perdre le green ✅ (livré 2026-06-30)
- `_amerge_work_item` reçoit le **worktree** et, sur conflit, **rebase la branche verte sur le HEAD à jour** (qui contient le commit du sibling) **dans son worktree** puis re-merge → le travail vert est préservé chaque fois que les éditions ne se chevauchent pas vraiment. *(C3)*
- Sur conflit réel (mêmes lignes), le **`rebase --abort` restaure la branche verte intacte** (jamais perdue côté branche) et l'item est requeue pour un rebuild depuis le HEAD à jour ; le repo et le worktree restent **propres** (pas d'état `MERGE_HEAD`/rebasing résiduel).
- Tests `test_merge_preserve.py` : merge sans conflit → vert livré ; conflit réel → `False` + repo propre + **branche verte préservée**.
- **Acceptance** : aucun green silencieusement écrasé ; sur conflit l'état git reste cohérent et la branche conserve le travail.

### P2b — Reprendre le green préservé (au lieu de rebuilder) ✅ (livré 2026-07-02)
La v1 de P2 préservait la branche verte *pendant* la tentative, mais le cleanup du
worker (`finally`) **supprimait la branche** : au requeue, le travail vert était
regénéré de zéro. P2b ferme ce trou :
- **`keep_branch`** : dès que l'item est vert et commité, sa branche survit au
  cleanup (requeue de conflit, stop coopératif, FAILED en attente d'un retry
  manuel) ; elle n'est supprimée qu'une fois **mergée** ou l'unité **re-découpée**.
- **`_aresume_green_branch`** : au passage suivant (requeue, retry, ou orphelin
  GREEN d'un crash dur dont le `finally` n'a jamais tourné), la branche préservée
  est **reprise** — checkout en worktree, **rebase sur le HEAD à jour**, puis
  **re-vérification réelle** (`_averify_resumed`, suite de tests sans agent dev) :
  verte → merge direct **sans aucun rebuild** ; rouge → le dev **repart de ce code**
  (plus de page blanche) ; rebase en conflit réel → branche abandonnée, rebuild
  propre comme avant.
- Tests `test_merge_preserve.py` (reprise/rebase/merge, branche vide ou en conflit
  abandonnée, `keep_branch`) + `test_split_on_failure.py` (requeue de conflit →
  reprise sans 2ᵉ passage dev).
- **Acceptance** : un conflit de merge ne coûte plus une régénération complète ;
  un orphelin GREEN dont la branche a survécu est mergé, pas rebuildé.

### P3 — Fiabiliser le frontend en worktree ✅ (livré 2026-06-30)
- **`_node_modules_usable(root)`** : sonde `.bin`/`vite` au lieu de la simple existence du dossier → détecte une jonction silencieusement cassée ou un dossier vide.
- **`_link_node_modules` renvoie un booléen** : True **uniquement** si la jonction résout vers un install utilisable (plus de confiance aveugle dans `mklink /J`). *(C7)*
- **Fallback réel** : si la jonction échoue/ne résout pas, **`npm ci`** (ou `install`) réel dans le worktree (`_anpm_install_in`) → la vérif `vitest`/`tsc` résout toujours.
- Le retour anticipé teste désormais l'**utilisabilité** (pas l'existence), donc un worktree avec un `node_modules` partiel est ré-installé.
- Tests `test_frontend_node_modules.py` (utilisabilité, jonction qui rapporte sa résolution, fallback quand la jonction échoue, jonction OK → pas de réinstall).
- **Acceptance** : `vitest`/`tsc` ne sont plus jamais « introuvables » en worktree.

### P4 — Sous-système d'indépendance (la demande centrale) ⭐
- **Modèle** : remplir `Task.files_hint` (renommer conceptuellement en `file_globs`), via le décomposeur. *(C10)*
- **Nouveau** : `orchestrator/independence.py` (§3.3) + tests purs.
- **Nouveau** : skill `task-independence` + persona `independence-judge` (§3.4).
- **Décomposeur** : prompt « atomiser au maximum + déclarer file_globs » (§3.2).
- **Scheduler** : consomme la **partition certifiée** ; parallélise les classes disjointes, sérialise le reste.
- **Acceptance** : sur un projet fullstack à plusieurs composants, seules les tâches à fichiers disjoints tournent en parallèle ; restauration de la perf parallèle **sans** régression de conflit.

### P6 — Re-décomposition adaptative sur échec ⭐ (« US trop grosse pour une session »)
Quand une story/tâche **n'arrive pas à passer au vert** après ses tentatives de dev,
au lieu de la marquer FAILED, l'**architecte la ré-analyse et la découpe plus finement**
en sous-tâches plus petites, avec des **tests plus granulaires** — qui se construisent
ensuite chacune dans leur sous-agent focalisé. Contre directement le problème de l'unité
trop volumineuse pour une seule fenêtre de contexte d'agent.
- Automatique : hook du worker sur **deux** déclencheurs (`_amaybe_split_on_failure`) :
  la branche « **rouge épuisé** » (tests jamais verts), **et** le « **conflit de merge
  persistant** » (item vert dont le merge échoue après toutes ses tentatives — un
  smell de dimensionnement : ses zones de fichiers percutent sans cesse celles des
  siblings ; des sous-tâches plus fines et disjointes débloquent). Les erreurs
  d'**infra** (AgentError, crash CLI) ne déclenchent **jamais** de split — un échec
  transitoire n'est pas un problème de taille. **Borné** par `split_depth`/
  `SPLIT_MAX_DEPTH` (défaut **2**, pour qu'une tâche d'une TS extraite
  puisse elle-même être re-découpée une fois — cf. RFC technical-stories), ON par
  défaut (`SPLIT_ON_FAILURE`).
- Manuel : bouton **✂️ Découper plus fin** sur une story/tâche en échec
  (`POST …/items/{id}/split`), force le découpage puis reprend le build.
- **Forme du découpage** (RFC `RFC-technical-stories.md`, source de vérité) : une
  **tâche** en échec dont le conteneur garde ≥ 1 autre tâche est **extraite en
  Technical Story** nommée et adressable (`technical=true`, `contract`, `parent_id`),
  contenant les sous-tâches plus fines ; les dépendants sont recâblés vers la TS
  (le work-graph résout « dépendre d'une story = ses tâches + celles de ses TS
  enfants », récursivement). Quand la tâche était la **seule** du conteneur (ou pour
  une **US** sans tâches), repli sur le découpage **in-place** en sous-tâches sœurs
  — jamais de conteneur vide. Le floor d'indépendance s'applique aux nouvelles tâches.

### P5 — DoD incrémentale ✅ (livraison partielle livrée 2026-07-02 ; profils hors-plan)
- **Progrès partiel** : livrer les stories vertes même si d'autres échouent ; un projet n'est « échoué » que si **0** story livrée. *(C9)*
- **Profils** : `auto` ne doit pas activer streams pour un produit clairement simple ; aligner `profiles.py` (api/cli par défaut, fullstack explicite).
- **Pourquoi différé** : les stories vertes sont déjà **construites et commitées** ; P5 ne change que la *sémantique de « done »* (livraison partielle), pas la correction ni la récupération. Avec **P6** (auto-split sur échec) + retry + **P2** (préservation du green), les échecs sont déjà adressés. À reprendre seulement si le besoin produit de « livrer partiellement » se confirme.
- **⚠️ À réévaluer avec P7** : l'argument du report tenait quand les échecs étaient
  des feuilles. Les **Technical Stories** ajoutent des conteneurs bloquants — une TS
  FAILED bloque ses dépendants et la perception « projet échoué » (C9) revient. Plus
  le système découpe fin, plus la livraison partielle redevient le maillon manquant.

### P7 — Technical Stories (proactives + réactives) 🚧 (en cours)
Spécifié par **`RFC-technical-stories.md`** (source de vérité). Une TS = une
`UserStory(technical=True)` avec `contract` et `parent_id` — conteneur de travail
technique affiché au niveau des US, adressable (rebuild/split/diff), résolu par le
work-graph. Deux moteurs : **réactif** (P6 : extraction au split-on-failure) et
**proactif** (le PO émet des TS dans le plan ; le critic de `REVIEW_PLAN`
recommande l'extraction des unités trop grosses, `po_revise` applique).
- Backend : `technical/contract/parent_id`, promotion dans `_split_task`,
  résolution récursive `parent_id` dans `build_work_graph` — livrés (tests
  `test_split_on_failure.py`, `test_technical_story_plan.py`).
- Frontend : badge 🔧, `contract`, fil d'Ariane `parent_id`, DepGraphPanel — en cours.
- **Acceptance** : une tâche trop grosse échouée devient une TS visible sur le board ;
  ses dépendants attendent ses feuilles ; aucun conteneur vide ; profondeur bornée.

### P8 — Pipeline PO proactif (la qualité du plan amont) 📋 (spécifié)
Spécifié par **`RFC-po-pipeline-v2.md`**. Ce plan-ci a soigné le versant **réactif**
(orchestration, récupération) ; la prochaine famille d'échecs est la **qualité du
plan amont** — chaque split-on-failure est par définition une erreur de
dimensionnement du PO. P8 ferme la boucle : Structure+Complexité estimée (S1) →
Spec par story avec verdict `resize` (S2) → Gherkin validé déterministiquement (S3),
un critic transversal par étape, et des **sizing lessons** issues des splits réels
réinjectées dans S1. Le proactif réduit le réactif — mesurable via §8.

---

## Clôture du plan initial (2026-06-30)
**P0, P1, P2, P3, P4, P6 livrés et testés** (491+ tests backend verts, 141 vitest, tsc clean). Le chemin parallèle streams+worktree est désormais **sûr** (indépendance prouvée, conflits sérialisés), **auto-récupérant** (orphelins reset, worker non-fatal, split-on-failure) et **sans perte de travail** (green préservé, repo propre, bookkeeping hors git). **P5 différé** (optionnel).

**Réouvert le 2026-07-02** après revue croisée plan/code : **P2b livré** (reprise du
green préservé), **P6 durci** (split sur conflit persistant, jamais sur erreur
d'infra, profondeur 2), **P7 en cours** (Technical Stories), **P8 spécifié**
(pipeline PO), **§8 à instrumenter** (calibration). La clôture de 2026-06-30
prouvait la *correction* (tests) ; la preuve d'*efficacité en run réel* passe par
les métriques du §8.

---

## 5. Gardes anti-régression (fichiers réels)

*(Liste réconciliée le 2026-07-02 — les noms initialement prévus
(`test_scheduler_serialization.py`, `test_build_resilience.py`,
`test_no_lost_green.py`, `test_orphan_recovery.py`, `test_repo_clean.py`)
n'existent pas : leur couverture vit dans les fichiers ci-dessous.)*

- `test_independence.py` : analyseur pur (overlap de globs → arêtes, injection de
  `depends_on` déterministe, partition, `file_globs` vide → sérialisé), garde-fou
  scheduler (jamais de co-run sur fichiers déclarés communs), pass global
  cross-story, crash worker isolé (C6), reset des orphelins (C8), commit sans
  bookkeeping (C4).
- `test_merge_preserve.py` : green livré sur merge propre ; conflit réel → repo
  propre + branche verte préservée (C3) ; **P2b** : `keep_branch`, reprise/rebase/
  merge de la branche préservée, abandon des branches vides ou en conflit.
- `test_split_on_failure.py` : P6 — split story/tâche, extraction en TS, récursion
  bornée, split sur **conflit de merge persistant**, requeue de conflit → reprise
  **sans second passage dev**, work-graph récursif des TS enfants.
- `test_technical_story_plan.py` : P7 — TS proactives émises par le PO dans le plan.
- `test_frontend_node_modules.py` : P3 — utilisabilité de `node_modules`, jonction,
  fallback `npm ci`.
- `test_restart.py` : clear des interactions au restart, orphelins relançables.

---

## 6. Rollout / flags

1. Mergez **P0** seul, vérifiez todo-list verte en série.
2. **P1-P3** sous un flag `STREAMS_SAFE` (sérialisation par défaut), tests verts.
3. **P4** : `independence.py` + juge derrière `INDEPENDENCE` (OFF), activez après tests.
4. Réactivez `STREAMS=1` **uniquement** profil `fullstack`, une fois P1-P4 stables.
5. **P5** en dernier (change la sémantique de « done »).

> Règle d'or : tant que l'indépendance n'est pas **prouvée** (analyseur déterministe **+** juge),
> on **sérialise**. La perf parallèle revient comme une **optimisation certifiée**, jamais un défaut.

---

## 8. Observabilité & calibration ✅ (instrumenté 2026-07-02) 📊

La clôture s'appuie sur des **tests** (correction) ; rien ne mesure encore
l'**efficacité en run réel**. Compteurs à persister **par build** dans
`ProjectState` :

- **splits réactifs** (P6) — chacun est, par définition, une erreur de
  dimensionnement du plan amont ;
- **attempts moyens par item** et **requeues de conflit de merge** — santé du
  découpage en zones disjointes (P4) ;
- **reprises P2b** (branche préservée mergée sans rebuild) vs **rebuilds** — tokens
  économisés ;
- **resets d'orphelins** et **crashs worker isolés** — santé de l'infra, à ne
  **jamais** compter comme signal de dimensionnement.

Double usage : (a) prouver que P4/P6/P2b sont des filets rarement sollicités et non
des béquilles permanentes ; (b) alimenter les **sizing lessons** du pipeline PO
(P8/RFC v2) — l'échec d'aujourd'hui dimensionne le plan de demain. Sans ces
métriques, impossible de savoir si le proactif (P8) réduit réellement le réactif.

**Livré (2026-07-02)** : `PlanCalibration` étendu (`merge_requeues`,
`p2b_resumes`, `orphan_resets`, `infra_retries`) et **tous les compteurs ont un
producteur** — dont `over_budget_tasks` mesuré sur l'empreinte réelle du commit
vert (`_arecord_footprint`). Livraison partielle (P5, `PARTIAL_DELIVERY`)
et budget infra séparé (`INFRA_MAX_RETRIES`) livrés. L'éval A/B du RFC
v2 §6 est exécutable : `scripts/eval_po_pipeline.py` (scripted gratuit,
`EVAL_PROVIDER=claude` pour la mesure réelle). L'UI expose le tout :
badge complexité S1, taxonomie des critères S2, marqueur spec incomplète,
bannière « Livraison partielle », bloc calibration dans « Revue du plan ».

---

## 7. Livré (2026-06-29) — 474 tests backend verts

**P0 (stabilité, code) :**
- C4 — `autospec-state.json` / `autospec-interactions.jsonl` ajoutés aux `.gitignore` de scaffold (`workspace.py`, `BOOKKEEPING_IGNORE`) **et** dé-trackés idempotemment dans `_aignore_bookkeeping` (appelé par `_agit_ensure_repo`). Les commits de story ne les embarquent plus.
- C6 — `_reap_done` n'effondre plus le build : un worker qui plante est isolé en FAILED (`_fail_item_by_id`), les siblings continuent. Le `except Exception` de `_abuild_work_item` ne relance plus (retry/FAIL gracieux).
- C8 — `_reset_orphan_items()` remet tout item IN_PROGRESS/GREEN/RED sans worker → TODO ; appelé au début de `aresume_build` (avant le filtre `to_build`, qui sinon sautait l'orphelin pour toujours).

**P4 (sous-système d'indépendance) :**
- `orchestrator/independence.py` (floor déterministe pur + `declared_overlap`).
- `Task.files_hint` enfin rempli : prompts `decompose_story` + `_streams_plan_block` demandent `file_globs` ; parsing dans `_adecompose_story` et `_build_tasks`.
- `_enforce_task_independence` injecte les `depends_on` (floor) à la création des tâches.
- Garde-fou scheduler `_item_claim` + `independence.declared_overlap` : deux items aux fichiers **déclarés** chevauchants ne tournent jamais en parallèle (sans jamais deadlock les claims non déclarés — gérés par le floor).
- Juge LLM optionnel : persona `independence-judge`, skill `task-independence`, prompt `independence_judge`, méthode `_ajudge_independence`, flag `INDEPENDENCE` (OFF).

**Durcissement supplémentaire :**
- H1 — `_reset_orphan_items()` aussi dans le `finally` de `_abuild_phase_streams` (stop/cancel laisse un état propre, relançable).
- H2 — `aretry_failed` désengluine aussi les orphelins (un projet bloqué sur un orphelin, pas un FAILED propre, redevient relançable).
- H3/H4 — évalués : le livelock de merge est déjà évité par le garde-fou P4c ; la vérif post-build agrégée est déjà couverte par `_asmoke_phase` + `_apply_definition_of_done` + `_aruntime_acceptance_phase`.

**Tests :** `tests/test_independence.py` (11) — analyseur pur, reproduction todo_list_2, garde-fou scheduler (jamais de co-run sur fichiers déclarés communs, les deux finissent DONE), reset orphelins, crash worker isolé, commit sans bookkeeping.

> Note config : `STREAMS=1` est **laissé activé** dans `backend/.env` — le chemin parallèle est désormais sécurisé par P4, donc le désactiver (hotfix P0 d'origine) n'est plus nécessaire. À basculer à 0 seulement pour un débogage ponctuel.

### 7bis. Suite à revue de code (P1/P2 corrigés)

- **P1#1 — conflits cross-stream sur un même fichier réel.** `claims_overlap`/`declared_overlap` comparent désormais les **chemins réels** quand les deux tâches ont des `file_globs` **déclarés** (stream-agnostique) : deux streams qui déclarent `README.md`/`.gitignore`/`main.py` à la racine **conflictent** et sont sérialisés. Le stream ne sert de disjoncteur que pour les claims **vides** (« tout le file_root »). Le test qui encodait la mauvaise hypothèse est inversé (`test_cross_stream_same_real_file_is_serialized`).
- **P1#2 — floor seulement intra-story.** Nouveau **pass global** `independence.declared_serialization` + `Pipeline._enforce_global_independence()` (appelé dans `_abuild_phase` après le juge) : injecte des `depends_on` pour **toute** paire de tâches (toutes stories/streams) aux globs **déclarés** chevauchants (ex. deux stories éditant `pyproject.toml`). Ne touche pas aux claims vides → pas de sur-sérialisation ni deadlock ; le résiduel (agent qui oublie `file_globs`) reste couvert par le re-queue de merge.
- **P2#1 — restart ne vidait pas les interactions live.** `InteractionStore.clear()` ajouté + appelé dans `arestart_from_scratch` (l'endpoint sert d'abord ce store mémoire → l'activité d'anciens items ne réapparaît plus après un restart sans redémarrage backend).
- **P2#2 — UI « Continuer le build » masqué pour un orphelin dormant.** `hasBuildableStory` (work.ts) inclut désormais `in_progress`/`green` (évalué uniquement en phase dormante via `canResumeBuild`, où ce sont des orphelins que le backend reset à la reprise).
- Tests : +5 backend (cross-stream réel sérialisé, disjoints parallèles, pass global cross-story, clear interactions), +1 frontend (orphelin dormant resumable). Backend 482 / vitest 141.
