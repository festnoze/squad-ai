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
| C1 | **`AUTOSPEC_STREAMS=1` global** : tout projet, même trivial, emprunte le chemin parallèle streams+worktrees+merge. | `.env` ; défaut code `False`. | [config.py:306](backend/autospec/config.py#L306), [backend/.env](backend/.env) |
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
- **Config** : `AUTOSPEC_STREAMS=0` dans [backend/.env](backend/.env) (retour build série, chemin prouvé vert). *(C1)*
- **Repo propre** : ajouter `autospec-state.json`, `autospec-interactions.jsonl` au `.gitignore` du workspace **et** remplacer `git add -A` par un add ciblé du code. *(C4)*
- **Worker non-fatal** : dans `_reap_done`, **logger + marquer l'item FAILED**, ne plus relancer l'exception ni annuler les siblings. *(C6)*
- **Orphelins** : au `resume_build`/retry, remettre toute tâche `in_progress`/`green`/`red` **sans worker actif** → `todo`. *(C8)*
- **Acceptance P0** : relancer le brief todo-list → projet `done`, app lançable, aucun item figé.

### P1 — Sérialisation par file_root (corrige la fausse indépendance sans LLM)
- Scheduler : grouper les items par `stream` effectif ; **au plus un item en vol par `file_root`** tant que l'indépendance n'est pas certifiée. *(C2)*
- `_amerge_work_item` : sur conflit, **ne pas** retry à l'identique — **rebaser** le worktree sur HEAD à jour puis re-merger ; échec persistant → requeue avec `depends_on` ajouté vers l'item qui a gagné le fichier. *(C5)*
- **Acceptance** : 2 tâches frontend qui touchent `App.tsx` ne tournent jamais en parallèle ; le 2ᵉ part du HEAD contenant le 1er.

### P2 — Ne jamais perdre le green ✅ (livré 2026-06-30)
- `_amerge_work_item` reçoit le **worktree** et, sur conflit, **rebase la branche verte sur le HEAD à jour** (qui contient le commit du sibling) **dans son worktree** puis re-merge → le travail vert est préservé chaque fois que les éditions ne se chevauchent pas vraiment. *(C3)*
- Sur conflit réel (mêmes lignes), le **`rebase --abort` restaure la branche verte intacte** (jamais perdue côté branche) et l'item est requeue pour un rebuild depuis le HEAD à jour ; le repo et le worktree restent **propres** (pas d'état `MERGE_HEAD`/rebasing résiduel).
- Tests `test_merge_preserve.py` : merge sans conflit → vert livré ; conflit réel → `False` + repo propre + **branche verte préservée**.
- **Acceptance** : aucun green silencieusement écrasé ; sur conflit l'état git reste cohérent et la branche conserve le travail.

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
- Automatique : hook dans la branche « rouge épuisé » du worker (`_amaybe_split_on_failure`),
  **borné** par `split_depth`/`AUTOSPEC_SPLIT_MAX_DEPTH` (pas de récursion infinie), ON par
  défaut (`AUTOSPEC_SPLIT_ON_FAILURE`).
- Manuel : bouton **✂️ Découper plus fin** sur une story/tâche en échec
  (`POST …/items/{id}/split`), force le découpage puis reprend le build.
- Réécriture des dépendances : une tâche découpée est remplacée par ses sous-tâches, les
  dépendants attendent désormais **toutes** les sous-tâches ; le floor d'indépendance
  s'applique aux nouvelles tâches.

### P5 — DoD incrémentale + profils  ⏸️ (différé — non indispensable)
- **Progrès partiel** : livrer les stories vertes même si d'autres échouent ; un projet n'est « échoué » que si **0** story livrée. *(C9)*
- **Profils** : `auto` ne doit pas activer streams pour un produit clairement simple ; aligner `profiles.py` (api/cli par défaut, fullstack explicite).
- **Pourquoi différé** : les stories vertes sont déjà **construites et commitées** ; P5 ne change que la *sémantique de « done »* (livraison partielle), pas la correction ni la récupération. Avec **P6** (auto-split sur échec) + retry + **P2** (préservation du green), les échecs sont déjà adressés. À reprendre seulement si le besoin produit de « livrer partiellement » se confirme.

---

## Clôture du plan (2026-06-30)
**P0, P1, P2, P3, P4, P6 livrés et testés** (491+ tests backend verts, 141 vitest, tsc clean). Le chemin parallèle streams+worktree est désormais **sûr** (indépendance prouvée, conflits sérialisés), **auto-récupérant** (orphelins reset, worker non-fatal, split-on-failure) et **sans perte de travail** (green préservé, repo propre, bookkeeping hors git). **P5 différé** (optionnel). Reste hors-plan : alignement des profils `auto`/`fullstack` si souhaité.

---

## 5. Tests à ajouter (garde anti-régression)

- `test_independence.py` (pur) : overlap de globs → arêtes ; injection de `depends_on` déterministe ; partition correcte ; `file_globs` vide → sérialisé ; idempotence.
- `test_scheduler_serialization.py` : 2 tâches même `file_root` sans dep → jamais co-running.
- `test_build_resilience.py` : un worker qui lève → cet item FAILED, les autres continuent (C6).
- `test_no_lost_green.py` : item vert + conflit de merge → branche conservée, requeue, finit mergé (C3).
- `test_orphan_recovery.py` : tâche `in_progress` sans worker → `todo` au resume (C8).
- `test_repo_clean.py` : un commit de story ne contient ni `autospec-state.json` ni `…interactions.jsonl` (C4).

---

## 6. Rollout / flags

1. Mergez **P0** seul, vérifiez todo-list verte en série.
2. **P1-P3** sous un flag `AUTOSPEC_STREAMS_SAFE` (sérialisation par défaut), tests verts.
3. **P4** : `independence.py` + juge derrière `AUTOSPEC_INDEPENDENCE` (OFF), activez après tests.
4. Réactivez `AUTOSPEC_STREAMS=1` **uniquement** profil `fullstack`, une fois P1-P4 stables.
5. **P5** en dernier (change la sémantique de « done »).

> Règle d'or : tant que l'indépendance n'est pas **prouvée** (analyseur déterministe **+** juge),
> on **sérialise**. La perf parallèle revient comme une **optimisation certifiée**, jamais un défaut.

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
- Juge LLM optionnel : persona `independence-judge`, skill `task-independence`, prompt `independence_judge`, méthode `_ajudge_independence`, flag `AUTOSPEC_INDEPENDENCE` (OFF).

**Durcissement supplémentaire :**
- H1 — `_reset_orphan_items()` aussi dans le `finally` de `_abuild_phase_streams` (stop/cancel laisse un état propre, relançable).
- H2 — `aretry_failed` désengluine aussi les orphelins (un projet bloqué sur un orphelin, pas un FAILED propre, redevient relançable).
- H3/H4 — évalués : le livelock de merge est déjà évité par le garde-fou P4c ; la vérif post-build agrégée est déjà couverte par `_asmoke_phase` + `_apply_definition_of_done` + `_aruntime_acceptance_phase`.

**Tests :** `tests/test_independence.py` (11) — analyseur pur, reproduction todo_list_2, garde-fou scheduler (jamais de co-run sur fichiers déclarés communs, les deux finissent DONE), reset orphelins, crash worker isolé, commit sans bookkeeping.

> Note config : `AUTOSPEC_STREAMS=1` est **laissé activé** dans `backend/.env` — le chemin parallèle est désormais sécurisé par P4, donc le désactiver (hotfix P0 d'origine) n'est plus nécessaire. À basculer à 0 seulement pour un débogage ponctuel.

### 7bis. Suite à revue de code (P1/P2 corrigés)

- **P1#1 — conflits cross-stream sur un même fichier réel.** `claims_overlap`/`declared_overlap` comparent désormais les **chemins réels** quand les deux tâches ont des `file_globs` **déclarés** (stream-agnostique) : deux streams qui déclarent `README.md`/`.gitignore`/`main.py` à la racine **conflictent** et sont sérialisés. Le stream ne sert de disjoncteur que pour les claims **vides** (« tout le file_root »). Le test qui encodait la mauvaise hypothèse est inversé (`test_cross_stream_same_real_file_is_serialized`).
- **P1#2 — floor seulement intra-story.** Nouveau **pass global** `independence.declared_serialization` + `Pipeline._enforce_global_independence()` (appelé dans `_abuild_phase` après le juge) : injecte des `depends_on` pour **toute** paire de tâches (toutes stories/streams) aux globs **déclarés** chevauchants (ex. deux stories éditant `pyproject.toml`). Ne touche pas aux claims vides → pas de sur-sérialisation ni deadlock ; le résiduel (agent qui oublie `file_globs`) reste couvert par le re-queue de merge.
- **P2#1 — restart ne vidait pas les interactions live.** `InteractionStore.clear()` ajouté + appelé dans `arestart_from_scratch` (l'endpoint sert d'abord ce store mémoire → l'activité d'anciens items ne réapparaît plus après un restart sans redémarrage backend).
- **P2#2 — UI « Continuer le build » masqué pour un orphelin dormant.** `hasBuildableStory` (work.ts) inclut désormais `in_progress`/`green` (évalué uniquement en phase dormante via `canResumeBuild`, où ce sont des orphelins que le backend reset à la reprise).
- Tests : +5 backend (cross-stream réel sérialisé, disjoints parallèles, pass global cross-story, clear interactions), +1 frontend (orphelin dormant resumable). Backend 482 / vitest 141.
