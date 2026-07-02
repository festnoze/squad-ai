# 03 — Composants majeurs du frontend Autospec

> Référence de reconstruction à l'identique. Couvre `Board.tsx`, `Activity.tsx`,
> `RunPanel.tsx`, `LlmActivity.tsx`, `ProjectBar.tsx` (React 18 + TypeScript),
> y compris tous les sous-composants internes définis dans ces fichiers.
> Les libellés cités sont les valeurs **FR** des namespaces i18n
> (`board.ts`, `activity.ts`, `runPanel.ts`, `llmActivity.ts`, `projectBar.ts`,
> `common.ts`). Tous les composants obtiennent `t` via `useI18n()`.

---

## Board (`frontend/src/components/Board.tsx`)

### Vue d'ensemble et constantes de module

Le Board est le panneau « Board Epics / User stories » : navigation hiérarchique
à 4 niveaux **epics → epic → us → task**, pilotée par un state local `nav`.

Constantes et helpers de module (hors composants) :

- `statusLabel(t, status)` : mappe un statut vers son libellé i18n :
  `todo`→`board.status_todo` (« À faire »), `in_progress`→« Dev en cours »,
  `red`→« Tests rouges », `green`→« Tests verts », `done`→« Terminé »,
  `failed`→« Échec ». Fallback : le statut brut.
- `isLiveStatus(status)` : `true` si `in_progress | red | green` (déclenche le
  polling live de `LlmActivity`).
- `testStateLabel(t, state)` : `nonexistent`→« inexistant », `red`→« rouge »,
  `green`→« vert ».
- `TEST_STATE_ICON` : `nonexistent: "○"`, `red: "●"`, `green: "●"` (la couleur
  vient du CSS via `state-<state>`).
- `STREAM_ICON` (par `StreamKind`) : `backend: "⚙"`, `frontend: "🎨"`,
  `cache: "⚡"`, `database: "🗄"`, `other: "📦"`.
- `streamLabel(t, kind)` : `backend`→« Backend », `frontend`→« Frontend »,
  `cache`→« Cache », `database`→« BDD », `other`→« Autre ».
- `stop(e)` : helper `e.stopPropagation()` réutilisé partout pour empêcher
  l'ouverture de la carte parente.
- `deriveEpicDeps(stories)` : dérive les dépendances inter-epics depuis les
  `depends_on` des US (l'epic A dépend de B si une US de A dépend d'une US de B,
  B ≠ A). Renvoie `Map<epicId, epicId[]>` triée et dédupliquée.
- `PLANNING_PHASES = ["spec", "analyze", "plan", "architect"]` (état vide
  « plan en cours »).

Diagramme général du Board :

```
┌─ .panel.board ────────────────────────────────────────────────┐
│ ┌─ .board-top ─────────────────────────────────────────────┐  │
│ │ h2 "Board Epics / User stories"   Breadcrumb Épics/E/US/T│  │
│ └──────────────────────────────────────────────────────────┘  │
│ [.stream-filter  (si multi-stream) : Tous les streams|⚙ b…]  │
│                                                                │
│ niveau "epics"        niveau "epic"          niveau "us"/"task"│
│ ┌.epic-grid────────┐  ┌.epic-view─────────┐  ┌.us-view───────┐│
│ │ ┌EpicCard┐ ┌────┐│  │ entête + progress │  │ [.us-tasks]   ││
│ │ │id  it.N│ │ …  ││  │ .stories          │  │  TaskRow…     ││
│ │ │titre   │ └────┘│  │  ┌StoryRow──────┐ │  │ StoryDetail / ││
│ │ │▓▓▓░ 2/3│       │  │  │⠿ US-1 badges │ │  │ TaskDetail    ││
│ │ └────────┘       │  │  │ tasks ▾      │ │  └───────────────┘│
│ └──────────────────┘  │  └──────────────┘ │                   │
│                       │ [+ Ajouter une US]│                   │
│                       └───────────────────┘                   │
└────────────────────────────────────────────────────────────────┘
```

### Board (composant exporté)

**Rôle** : conteneur racine du board, gère la navigation, le filtre stream, les
états vides et la résolution des ids contre les props (rafraîchies en live par
WebSocket).

**Props** (`interface Props`) :

| Prop | Type | Oblig. |
|---|---|---|
| `epics` | `Epic[]` | oui |
| `stories` | `UserStory[]` | oui |
| `streams` | `Stream[]` | non (absent/vide = projet legacy mono-stream) |
| `projectId` | `string` | oui |
| `phase` | `string` | non |
| `focus` | `{ epicId: string; storyId?: string } \| null` | non — cible de navigation externe (vue Itérations) |
| `onFocusConsumed` | `() => void` | non — appelé une fois `focus` appliqué |
| `onOpenIteration` | `(iter: number) => void` | non — bascule vers la vue Itérations |

**State / effects** :
- `nav: Nav` (`{ level: "epics"|"epic"|"us"|"task", epicId?, storyId?, taskId? }`),
  init `{ level: "epics" }`.
- `streamFilter: string` (`""` = tous les streams). Uniquement proposé si
  `streams.length > 1`.
- `primaryStreamId` (useMemo) : stream `primary`, sinon premier `kind==="backend"`,
  sinon premier stream, sinon `"backend"`.
- `useEffect [focus, onFocusConsumed]` : applique `focus` → `nav` niveau `us`
  (si `storyId`) ou `epic`, puis appelle `onFocusConsumed?.()`.
- **Résolution défensive** : `epic`, `story`, `task` sont re-résolus à chaque
  rendu contre les props ; un élément sélectionné disparu fait remonter d'un
  niveau (`level` recalculé) au lieu d'afficher du vide.
- `openTaskById(taskId)` : retrouve la story propriétaire (celle dont
  `tasks` contient l'id) et navigue au niveau `task`.
- `openTask(storyId, taskId)` : navigation directe.

**État vide** (`epics.length === 0`) — rendu alternatif complet :

```
div.panel.board.empty
  h2                                    → board.boardTitle « Board Epics / User stories »
  div.board-empty
    (si phase ∈ PLANNING_PHASES)
      span.spinner (aria-hidden)
      p.placeholder                     → board.empty_planning
        « Le PM/PO génère le plan… les épics et user stories apparaîtront ici. »
    (sinon si phase === "build")
      p.placeholder                     → board.empty_building
        « Construction en cours… le plan va s'afficher. »
    (sinon)
      p.placeholder                     → empty_noPlan_before + <strong>empty_noPlan_execution</strong> + empty_noPlan_after
        « Pas encore de plan. Lance la spécification depuis le panneau <strong>Exécution</strong> ci-dessous pour générer épics & user stories. »
```

**Structure DOM (état normal)** :

```
div.panel.board
  div.board-top
    h2                                  → « Board Epics / User stories »
    <Breadcrumb …/>
  (si multiStream)
    div.stream-filter [role=group, aria-label=board.streamFilter_aria « Filtre par stream »]
      button[.active si filtre=""] [aria-pressed]   → board.streamFilter_all « Tous les streams »
      button×N [data-testid=stream-filter-<id>]     → "<STREAM_ICON[kind]> <id>"  (toggle : re-clic = désactive)
  (level === "epics")  <EpicsView …/>
  (level === "epic")   <EpicView …/>
  (level === "us")
    div.us-view
      (si story.tasks non vide)
        div.us-tasks [data-testid=us-tasks-<storyId>]
          h4                            → board.tasksHeading « Tâches ({count}) »
          div.tasks > <TaskRow …/>×N
      <StoryDetail …/>
  (level === "task")
    div.us-view > <TaskDetail …/>
```

**Interactions** : clic sur un bouton du filtre stream → `setStreamFilter`
(toggle) ; navigation via Breadcrumb / cartes / lignes (callbacks `setNav`).

---

### StreamBadge (interne)

**Rôle** : badge de stream (icône + libellé, couleur par kind via CSS). Résout
l'id vers le stream déclaré ; id inconnu → libellé générique du kind. Rendu
uniquement quand l'item porte un stream ≠ stream primaire.

**Props** : `streamId: string` (oblig.), `streams: Stream[]` (oblig.).

**DOM** :
```
span.stream-badge.stream-badge-<kind> [data-testid=stream-badge-<streamId>]
  [title = board.streamBadge_title « Stream « {id} » ({kind}) »]
  texte : "<icône> <stream.id>"  ou  "<icône> <libellé kind>" si id inconnu
```

### BlockedBadge (interne)

**Rôle** : badge « bloquée par X » (ST-14) pour un item `todo` avec dépendances
non satisfaites. Rend `null` si `blockers` vide.

**Props** : `blockers: string[]` (oblig.).

**DOM** :
```
span.blocked-badge [data-testid=blocked-badge]
  [title = board.blocked_title « En attente d'une dépendance non terminée »]
  texte : "⛔ " + board.blocked_label « bloquée par {blockers} » (join ", ")
```

### MergeBadge (interne)

**Rôle** : indice d'état de merge (ST-14), dérivé par `mergeState(status, lastError)`
(types.ts) : `done` → « merged » ; `failed` + erreur matchant
`/conflit de merge|merge conflict/i` → « conflict » ; sinon `null`.

**Props** : `status: StoryStatus` (oblig.), `lastError?: string`.

**DOM** :
- merged : `span.merge-badge.merge-ok [data-testid=merge-badge]`
  [title=`board.merge_ok_title` « Code mergé »] → `✓ mergé` (`merge_ok_label`).
- conflict : `span.merge-badge.merge-conflict [data-testid=merge-badge]`
  [title=`board.merge_conflict_title` « Échec sur conflit de merge inter-stream »]
  → `✗ conflit de merge` (`merge_conflict_label`).

### IterationBadge (interne)

**Rôle** : pastille « itération N ». Hyperlien vers la vue Itérations si
`onOpen` fourni, sinon simple libellé.

**Props** : `iteration: number` (oblig.), `onOpen?: (iter) => void`,
`compact?: boolean`.

**DOM** :
- sans `onOpen` : `span.epic-iter` → `it. {n}` (compact, `board.iteration_compact`)
  ou `itération {n}` (`board.iteration_full`).
- avec `onOpen` : `button.epic-iter.epic-iter-link`
  [title=`board.iteration_title` « Voir l'itération {n} dans la chronologie »]
  → `🕒 <label>`. Clic : `stop(e)` puis `onOpen(iteration)`.

### CriterionRow (interne)

**Rôle** : ligne dépliable d'un critère d'acceptance dans `StoryDetail`. L'état
du critère vient de `criterionState(story, criterion)` (types.ts : story `done`
→ green ; un test red → red ; tous verts → green ; sinon nonexistent).

**Props** : `story: UserStory` (oblig.), `criterion: AcceptanceCriterion` (oblig.).

**State** : `open: boolean` (init `false`).

**Dérivation** : `tests` = `story.test_plan` filtrés sur
`test.criteria.includes(criterion.id)` (avec `?? []` pour les anciens états).

**DOM** :
```
div.criterion.state-<state> [data-testid=criterion-<id>]
  div.criterion-head [data-testid=criterion-head-<id>]  (clic → toggle open)
    span.state-dot.state-<state>        → TEST_STATE_ICON[state]  (○ ou ●)
    span.criterion-text                 → criterion.text
    span.state-tag.state-<state> [data-testid=criterion-state] → « inexistant/rouge/vert »
    span.criterion-expander             → "▾" ouvert / "▸" fermé
  (si open)
    div.criterion-body
      h5                                → board.acceptanceTests_heading « Tests d'acceptance ({count}) »
      (si 0 test) p.placeholder.small   → board.noUnitTest « Aucun test unitaire rattaché — couvert par le test fonctionnel Gherkin ci-dessous. »
      (sinon) ul.criterion-tests > li×N
        span.state-dot.state-<status>   → ○/●
        span.test-layer                 → test.layer || "?"
        span.test-desc                  → test.description
        (si mocks) span.test-mocks      → " · " + board.testMocks « mocks : {mocks} »
        span.state-tag.state-<status>   → libellé état
      (si story.gherkin)
        h5                              → board.gherkinAssociated « Gherkin associé »
        pre.gherkin                     → story.gherkin
```

### StoryEditor (interne)

**Rôle** : formulaire d'édition inline d'une US (dans `StoryDetail`).

**Props** : `projectId: string` (oblig.), `story: UserStory` (oblig.),
`onClose: () => void` (oblig.).

**State** : `draft: EditDraft` (`{ title, description, priority, gherkin,
criteria: {id?, text}[] }`, initialisé depuis la story), `error: string`,
`saving: boolean`. Helpers : `setCriterion(i, text)`, `removeCriterion(i)`,
`addCriterion()` (ajoute `{ text: "" }`).

**API** : `save()` → `editStory(projectId, story.id, patch)` en filtrant les
critères vides (`text.trim() !== ""`) ; succès → `onClose()` ; erreur →
`errorMessage(e)` + `saving=false`.

**DOM** :
```
div.story-editor (onClick=stop)
  label.edit-field > span « Titre » (board.field_title) + input (title)
  label.edit-field > span « Description » + textarea rows=2
  label.edit-field > span « Priorité (1=haute) » (board.field_priority) + input[type=number, min=1, max=5]
  div.edit-field
    span « Critères d'acceptance » (board.field_criteria)
    div.edit-criteria
      div.edit-criterion-row ×N
        input [placeholder=board.criterion_placeholder « Critère… »]
        button.danger.small-btn [title=board.removeCriterion_title « Supprimer ce critère »] → "✕"
      button.ghost.small-btn                → board.addCriterion « + critère »
  label.edit-field > span « Gherkin » + textarea.mono rows=4
  (si error) div.edit-error
  div.edit-actions
    button.primary [disabled=saving]        → common.save « Enregistrer »
    button.ghost   [disabled=saving]        → common.cancel « Annuler »
```

### DiffBody (interne)

**Rôle** : rendu ligne-par-ligne d'un diff avec coloration.

**Props** : `diff: string` (oblig.).

**DOM** : `pre.diff-pre` contenant un `span` par ligne :
classe `diff-add` si la ligne commence par `+` (hors `+++`), `diff-del` si `-`
(hors `---`), sinon aucune. Le `\n` est ré-ajouté sauf sur la dernière ligne.

### DiffViewer (interne)

**Rôle** : overlay de diff réutilisable story OU task (l'appelant fournit le
label et le fetcher `storyDiff`/`taskDiff`).

**Props** : `label: string` (oblig.), `fetcher: () => Promise<{available, diff}>`
(oblig.), `onClose: () => void` (oblig.).

**State/effect** : `loading` (init `true`), `error`, `diff`, `available`.
`useEffect [label]` : fetch avec flag `cancelled` (cleanup).

**DOM** :
```
div.diff-overlay (clic → onClose)
  div.diff-panel (clic → stopPropagation)
    div.diff-header
      span.diff-title                     → "📊 " + board.diff_title « Diff — {label} »
      button.ghost.diff-close [aria-label=common.close « Fermer »] → "✕"
    div.diff-content
      (loading)  div.diff-muted           → common.loading « Chargement… »
      (error)    div.diff-error           → message
      (vide)     div.diff-muted           → board.diff_none « Aucun diff disponible pour cette story. »
      (sinon)    <DiffBody diff/>
```

### TechnicalBadge (interne)

**Rôle** : marqueur 🔧 d'une Technical Story (RFC technical-stories). Rend `null`
si `!story.technical`.

**Props** : `story: UserStory` (oblig.).

**DOM** : `span.badge-technical` [title=`board.technicalStory_title`
« Technical Story : conteneur non-fonctionnel de sous-tâches plus fines (extraite
d'une tâche trop grosse) »] → `🔧 Technique` (`board.technicalStory`).

### StoryBadges (interne)

**Rôle** : badges communs d'une US (priorité, statut, scores). Le statut affiché
est l'« effective status » (`usEffectiveStatus` : US conteneur → dérivé des
tâches : tout done→done, un actif→in_progress, un failed→failed, sinon todo).

**Props** : `story: UserStory` (oblig.), `onStatusClick?: () => void` (si
fourni, le badge statut devient un bouton ouvrant la vue LLM).

**DOM** :
```
span.story-right
  span.prio.prio-<priority> [title=board.prio_title « Priorité kanban (1=haute) »] → "P<priority>"
  (statut : contenu = [span.spinner.spinner-sm si in_progress] + libellé)
    avec onStatusClick : button.badge.badge-<status>.badge-btn
      [title=board.statusBadge_title « Voir les appels LLM de cet item », data-testid=status-badge-<id>]
      → "<statusInner> 🧠"   (clic : stop + onStatusClick)
    sinon : span.badge.badge-<status> → statusInner
  (si quality_score >= 0)        span.quality-badge  [title=board.quality_title « Qualité du code (raffinement) »]        → "⚙ {score}/100"
  (si mutation_score >= 0)       span.mutation-badge [title=board.mutation_title « Robustesse des tests (mutation testing) »] → "🧬 {score}/100"
  (si coverage_score >= 0)       span.coverage-badge [title=board.coverage_title « Couverture de tests »]                → "📊 {score}%"
```

### TaskRow (interne)

**Rôle** : ligne d'une tâche dans la sous-liste d'une US (et dans `us-view`).
Porte badge stream, statut avec spinner, blocked-by, merge ; clic → détail tâche.

**Props** : `task: Task`, `stories: UserStory[]`, `streams: Stream[]`,
`primaryStreamId: string`, `onOpen: () => void` (tous oblig.).

**Dérivation** : `blockers = blockedBy(task.depends_on, task.status, stories)` ;
`showStream = !!task.stream && task.stream !== primaryStreamId`.

**DOM** :
```
div.task-row.status-<status> [data-testid=task-<id>, role=button, tabIndex=0]
  (clic ou Enter/Espace → onOpen)
  span.task-id                            → task.id
  (si showStream) <StreamBadge/>
  span.task-title                         → task.title || task.id
  span.badge.badge-<status>               → [spinner si in_progress] + libellé statut
  <BlockedBadge blockers/>
  <MergeBadge status lastError/>
```

### StoryRow (interne)

**Rôle** : carte compacte cliquable d'une US (niveau « epic »). Clic → détail ;
poignée ⠿ dédiée au drag-&-drop de tri ; sous-liste de tâches dépliable.

**Props** : `story: UserStory`, `stories: UserStory[]` (toutes, pour blocked-by
cross-stream), `streams: Stream[]`, `primaryStreamId: string`,
`onOpen: () => void`, `onOpenTask: (taskId: string) => void`,
`dragOver: boolean`, `onHandleDragStart / onCardDragOver / onCardDragLeave /
onCardDrop: (e: React.DragEvent) => void` — toutes obligatoires.

**State** : `expanded: boolean` (init **true** — tâches dépliées par défaut).

**Dérivation** : `effStatus = usEffectiveStatus(story)` ; `blockers` ;
`showStream` (comme TaskRow).

**DOM** :
```
div.story.status-<effStatus>[.drag-over si dragOver]
  [data-testid=story-<id>, role=button, tabIndex=0]
  (clic ou Enter/Espace → onOpen ; onDragOver/onDragLeave/onDrop → callbacks)
  div.story-head
    span.drag-handle [draggable, onDragStart=onHandleDragStart, onClick=stop,
      title=board.dragHandle_title « Glisser pour réordonner »,
      aria-label=board.dragHandle_aria « Poignée de déplacement »]  → "⠿"
    span.story-id                         → story.id
    <TechnicalBadge/>
    (si showStream) <StreamBadge/>
    <StoryBadges story/>                  (sans onStatusClick)
  div.story-title                         → story.title
  (si depends_on non vide)
    div.story-deps                        → "⛓ " + board.dependsOn « dépend de {deps} »
  div.story-row-hints
    <BlockedBadge/> <MergeBadge/>
  (si tasks non vide)
    div.task-list (onClick=stop)
      button.task-list-toggle [data-testid=task-toggle-<id>]   (clic → toggle expanded)
        → "▾ "/"▸ " + board.tasks_count(_plural) « {count} tâche(s) »
      (si expanded) div.tasks [data-testid=tasks-<id>] > <TaskRow/>×N
  div.story-open-hint                     → "▸ " + board.storyOpenHint « détails »
```

### StoryDetail (interne)

**Rôle** : vue détaillée d'une US (niveau « us ») : description, toolbar
d'actions, critères (tests + Gherkin), dernière erreur, vue LLM et diff.

**Props** : `projectId: string`, `story: UserStory`, `phase?: string`,
`onDeleted: () => void`, `onOpenIteration?: (iter) => void`.

**State** : `editing`, `error`, `busy`, `showDiff`, `showLlm` (tous booléens/
string init faux/vide).

**Logique** :
- `run(fn)` : wrapper anti double-clic (busy) + affichage `errorMessage`.
- Actions API : `rebuildStory`, `forceDoneStory`, `splitItem`, `deleteStory`
  (avec `window.confirm(board.confirmDeleteStory « Supprimer la user story
  « {title} » ? »)`).
- `dormant = phase ∈ ["done","stopped","error"]`.
- `stuck = status==="failed" || status==="red" || (status==="todo" && (attempts>0 || last_error))`.
- `canRelaunch = dormant && stuck` ; `canSplit = dormant && status==="failed"`.

**DOM** :
```
div.story-detail
  div.story-detail-head
    span.story-id → story.id
    <TechnicalBadge/>
    <IterationBadge iteration onOpen=onOpenIteration compact/>
    <StoryBadges story onStatusClick=toggle showLlm/>
  h3.story-detail-title → story.title
  (si technical && parent_id)
    div.story-ts-lineage → "🔧 " + board.technicalStory_from « Extraite de {parent} »
  (si technical && contract)
    div.story-ts-contract
      div.story-ts-contract-heading → board.technicalContract « Contrat technique »
      pre.gherkin → story.contract
  (si depends_on) div.story-deps → "⛓ dépend de {deps}"
  (si editing) <StoryEditor/>
  (sinon)
    div.story-toolbar
      button.ghost.small-btn                → "✏️ Éditer" (board.action_edit)
      button.danger.small-btn               → "🗑 Supprimer" (board.action_delete)
      (si canRelaunch)
        button.action-btn.small-btn [disabled=busy, title=board.relaunchStory_title
          « Réinitialiser et reconstruire cette user story »]     → "🔄 Relancer" (action_relaunch)
        button.action-btn.action-done.small-btn [title=board.forceDoneStory_title
          « Marquer cette user story comme terminée sans la reconstruire »] → "✓ Forcer terminé" (action_forceDone)
        (si canSplit)
          button.action-btn.small-btn [title=board.splitItem_title « Ré-analyser cette unité en échec
            et la découper en sous-tâches plus fines (trop grosse pour une session d'agent),
            puis reprendre le build »]                            → "✂️ Découper plus fin" (action_split)
      (si status==="done") button.action-btn.small-btn            → "🔁 Rejouer" (action_replay, → rebuildStory)
      (si status==="done") button.ghost.small-btn                 → "📊 Diff" (action_diff, → showDiff)
    (si error) div.edit-error
    p → story.description
    (si acceptance_criteria)
      h4 → board.acceptanceCriteria_heading « Critères d'acceptance »
      div.criteria > <CriterionRow/>×N
    (si last_error)
      h4 → board.lastError_heading « Dernière erreur »
      pre.error-output → story.last_error
  (si showLlm && !editing) <LlmActivity projectId itemId=story.id live=isLiveStatus(effectiveStatus)/>
  (si showDiff) <DiffViewer label=story.id fetcher=storyDiff onClose/>
```

### TaskDetail (interne)

**Rôle** (ST-13) : vue détaillée d'une tâche, miroir de `StoryDetail` : stream,
critères, dépendances (blocked-by), état de merge, dernière erreur, actions
Relancer / Forcer terminé / Découper / Rejouer / Diff.

**Props** : `projectId: string`, `task: Task`, `stories: UserStory[]`,
`streams: Stream[]`, `primaryStreamId: string`, `phase?: string`.

**State** : `error`, `busy`, `showDiff`, `showLlm`. Même wrapper `run(fn)`.

**Logique** : `dormant`/`stuck`/`canRelaunch`/`canSplit` identiques à
StoryDetail (sur `task`) ; `blockers = blockedBy(task.depends_on, task.status,
stories)` ; `showStream` idem.

**DOM** :
```
div.story-detail [data-testid=task-detail-<id>]
  div.story-detail-head
    span.story-id → task.id
    (si showStream) <StreamBadge/>
    button.badge.badge-<status>.badge-btn [title=board.taskStatusBadge_title
      « Voir les appels LLM de cette tâche », data-testid=status-badge-<id>]
      → [spinner si in_progress] + libellé + " 🧠"   (clic → toggle showLlm)
    <MergeBadge/>
  h3.story-detail-title → task.title || task.id
  (si depends_on) div.story-deps → "⛓ dépend de {deps}"
  div.story-row-hints > <BlockedBadge/>
  div.story-toolbar
    (si canRelaunch) "🔄 Relancer" [title=board.relaunchTask_title « Réinitialiser et
      reconstruire cette tâche »] + "✓ Forcer terminé" [title=board.forceDoneTask_title
      « Marquer cette tâche comme terminée sans la reconstruire »]
      + (si canSplit) "✂️ Découper plus fin"
    (si done) "🔁 Rejouer" + "📊 Diff"     (mêmes classes que StoryDetail)
  (si error) div.edit-error
  (si description) p
  (si acceptance_criteria) h4 « Critères d'acceptance » + ul.task-criteria > li (texte simple)
  (si gherkin) h4 « Gherkin » (board.field_gherkin) + pre.gherkin
  (si last_error) h4 « Dernière erreur » + pre.error-output
  (si showLlm) <LlmActivity itemId=task.id live=isLiveStatus(task.status)/>
  (si showDiff) <DiffViewer label=task.id fetcher=taskDiff/>
```

### AddStoryForm (interne)

**Rôle** : ajout manuel d'une US sous un epic (bouton repliable → formulaire).

**Props** : `projectId: string`, `epicId: string` (oblig.).

**State** : `open` (init false), `title`, `description`, `priority` (init 3),
`error`, `saving`. `reset()` remet tout à zéro et referme.

**API** : `submit()` → validation titre non vide (`board.titleRequired`
« Le titre est requis. ») puis `addStory(projectId, { epic_id, title,
description?, priority })`.

**DOM** :
- fermé : `button.ghost.add-story-btn` → `board.addStory` « + Ajouter une US ».
- ouvert :
```
div.add-story-form
  label.edit-field > span « Titre * » (board.field_titleRequired) + input
  label.edit-field > span « Description » + textarea rows=2
  label.edit-field > span « Priorité (1=haute) » + input[type=number 1..5]
  (si error) div.edit-error
  div.edit-actions
    button.primary [disabled=saving] → board.create « Créer »
    button.ghost   [disabled=saving] → « Annuler »
```

### EpicStories (interne)

**Rôle** : liste des US d'un epic, **triée par priorité croissante (tri stable)**
et réordonnançable par drag-&-drop via la poignée.

**Props** : `projectId: string`, `stories: UserStory[]` (celles de l'epic,
éventuellement filtrées par stream), `allStories: UserStory[]` (toutes — pour le
blocked-by cross-stream), `streams: Stream[]`, `primaryStreamId: string`,
`onOpen: (storyId) => void`, `onOpenTask: (taskId) => void`.

**State** : `draggingId: string | null`, `overId: string | null`, `error`.

**Logique DnD** : `handleDrop(targetId)` — retire l'id source de la liste
ordonnée, l'insère à l'index de la cible, recalcule les priorités
`min(index+1, 5)`, appelle `reorderStories(projectId, priorities)`. Pas de
re-fetch (le backend diffuse le nouvel état via WebSocket). Erreur →
`board.reorderFailed` « Échec du réordonnancement : {error} ».
Les callbacks passés à `StoryRow` : dragstart poignée (`effectAllowed="move"`),
dragover carte (`preventDefault` + `setOverId`), dragleave (reset si courant),
drop (`preventDefault` + `handleDrop`). `dragOver` vrai pour la carte survolée
si un drag est actif et que ce n'est pas la carte source.

**DOM** : `div.stories` > `[div.edit-error?]` + `<StoryRow/>×N`.

### Breadcrumb (interne)

**Rôle** : fil d'Ariane « Épics / EPIC-x / US-y / TASK-z », chaque ancêtre
cliquable.

**Props** : `epic: Epic | null`, `story: UserStory | null`, `taskId?: string | null`,
`onNavEpics: () => void`, `onNavEpic: () => void`, `onNavStory: () => void`.

**DOM** :
```
nav.breadcrumb [aria-label=board.breadcrumb_aria « Fil d'Ariane »]
  button.crumb [disabled si !epic && !story]  → board.breadcrumb_epics « Épics »
  (si epic)  span.crumb-sep "/" + (story ? button.crumb → epic.id : span.crumb.current → epic.id)
  (si story) span.crumb-sep "/" + (taskId ? button.crumb → story.id : span.crumb.current → story.id)
  (si taskId) span.crumb-sep "/" + span.crumb.current → taskId
```

### epicProgress (fonction exportée) et EpicProgressBar (exporté)

`epicProgress(stories): EpicProgress` — compte par statut **effectif**
(`usEffectiveStatus`) : `{ total, done, inProgress, failed, pct, state }` ;
`pct = round(done/total*100)` (0 si vide) ; `state` : `inProgress>0`→`working`,
sinon `failed>0`→`failed`, sinon tout done→`done`, sinon `pending`. Réutilisé
par la vue Itérations. Type `EpicState = "working"|"failed"|"done"|"pending"`.

**EpicProgressBar** — **Props** : `prog: EpicProgress` (oblig.). **DOM** :
```
div.epic-progress [role=progressbar, aria-valuenow=pct, aria-valuemin=0, aria-valuemax=100,
  title=board.progress_title « {done}/{total} terminée(s) — {pct}% »]
  div.epic-progress-fill.state-<state> [style width:<pct>%]
div.epic-card-meta
  texte → board.progress_done « {done}/{total} terminée(s) »
  (si inProgress>0) span.epic-meta-working → " · " + « {count} en cours » (progress_inProgress)
  (si failed>0)     span.epic-meta-failed  → " · " + « {count} en échec » (progress_failed)
```

### EpicCard (interne)

**Rôle** : carte epic cliquable (niveau racine) : avancement + halo « working ».

**Props** : `epic: Epic`, `stories: UserStory[]` (toutes), `epicDeps:
Map<string, string[]>`, `onOpenEpic: (epicId) => void`,
`onOpenIteration?: (iter) => void`.

**Dérivation** : `es = stories` filtrées sur `epic_id` ; `prog = epicProgress(es)` ;
`deps = epicDeps.get(epic.id) ?? []`.

**DOM** :
```
div.epic.epic-card.epic-<state> [data-testid=epic-<id>, role=button, tabIndex=0]
  (clic ou Enter/Espace → onOpenEpic)
  div.epic-head
    span.epic-id → epic.id
    span.epic-head-right
      (si state==="working") span.spinner [data-testid=epic-spinner,
        title+aria-label=board.developmentInProgress « Développement en cours »]
      <IterationBadge iteration=epic.iteration onOpen compact/>
  div.epic-title → epic.title
  (si description) p.epic-desc
  <EpicProgressBar prog/>
  (si deps) div.story-deps → "⛓ dépend de {deps}"
```

### EpicsView (interne)

**Rôle** : niveau racine — vision produit à plat, tous les epics dans une grille
unique (la dimension temporelle vit dans la vue « Itérations »).

**Props** : `epics: Epic[]`, `stories: UserStory[]`, `epicDeps: Map<string,
string[]>`, `onOpenEpic: (epicId) => void`, `onOpenIteration?: (iter) => void`.

**DOM** : `div.epic-grid` > `<EpicCard/>×N`.

### EpicView (interne)

**Rôle** : niveau epic — description + liste des US (drag-&-drop, ajout),
filtrable par stream (ST-12 : une US est gardée si elle-même OU une de ses
tâches touche le stream — helper `storyTouchesStream`). La barre d'avancement
est calculée sur **toutes** les US de l'epic (non filtrées).

**Props** : `projectId: string`, `epic: Epic`, `stories: UserStory[]` (toutes),
`streams: Stream[]`, `primaryStreamId: string`, `streamFilter: string`
(`""` = tous), `epicDeps: Map<string, string[]>`, `onOpenStory: (storyId) => void`,
`onOpenTask: (taskId) => void`, `onOpenIteration?: (iter) => void`.

**DOM** :
```
div.epic-view.epic-<state>
  div.epic-head
    span.epic-id → epic.id
    <IterationBadge iteration onOpen/>          (forme longue « itération {n} »)
  h3.epic-view-title
    (si working) span.spinner [title+aria-label « Développement en cours »]
    epic.title
  (si description) p.epic-view-desc
  <EpicProgressBar/>
  (si deps) div.story-deps → "⛓ dépend de {deps}"
  <EpicStories stories=filtrées allStories=toutes …/>
  <AddStoryForm projectId epicId/>
```

---

## Activity (`frontend/src/components/Activity.tsx`)

### Vue d'ensemble

Surface canonique du build (P6) : une ligne (Stepper) par work item (US ou
tâche), nourrie par `buildWorkGraph` (work.ts) + le heartbeat `ProjectTicks`.
Header avec compteurs, chip « à traiter », raison de stall ; bannière
d'approbation ; rail « Équipe » (filtre par persona) ; région épinglée « À
traiter » pour les items failed/blocked.

Constantes de module :

- `isLive(status)` : identique à `isLiveStatus` du Board.
- `PERSONA_META` (icône + clé i18n) : `dev: 👨‍💻/personaDev « Dev »`,
  `qa: 🧪/« QA »`, `critic: 🔍/« Critique »`, `judge: ⚖️/« Juge »`,
  `architect: 🏛️/« Architecte »`, `analyst: 📊/« Analyste »`,
  `pm: 📋/« PM »`, `po: 🗂/« PO »`.
- `GUIDANCE_STATUS_KEY` : `queued`→`activity.guidanceQueued` « en file »,
  `applied`→« appliquée », `too_late`→« trop tard ».
- `stallLabel(reason, t)` : `merge_lock_held:<id>` → `activity.stallMergeLock`
  « Merge en cours (verrou détenu par {holder}) » ;
  `awaiting_approval` → « En attente d'une validation » ;
  `budget_paused` → « Budget atteint — en pause » ; sinon la raison brute.
- `itemSource(item, storyById, taskById)` : résout la story/tâche persistée.
- `needsAttention(view, blockers)` : `status ∈ {failed, red}` ou
  `stage === "failed"` ou `blockers.length > 0`.

Diagramme :

```
┌─ section.panel.activity [region "Activité"] ────────────────────────────┐
│ ┌ .activity-header ──────────────────────────────────────────────────┐  │
│ │ h2 "⚡ Activité"  [2 en cours][1 en file][5 faits][1 échecs]        │  │
│ │ [⚠ 2 à traiter]  [⏸ raison de stall]                               │  │
│ └────────────────────────────────────────────────────────────────────┘  │
│ [.approval-banner ⏸ Validation requise — <phase>  ✅ Approuver ✋ Rejeter]│
│ ┌ .activity-body ───────────────────────────────────────────────────┐   │
│ │ ┌.crew-rail──────┐ ┌.activity-rows-wrap───────────────────────┐   │   │
│ │ │ ▾ Équipe       │ │ ┌ À traiter (région épinglée) ─────────┐ │   │   │
│ │ │ [Tous]         │ │ │ ActivityRow (attention)…             │ │   │   │
│ │ │ [👨‍💻 Dev (2)]  │ │ └──────────────────────────────────────┘ │   │   │
│ │ │ [🧪 QA (1)]    │ │ .activity-rows                           │   │   │
│ │ └────────────────┘ │  ▸ US-1 👨‍💻 Dev  titre  [Stepper]  ⋯     │   │   │
│ │                    │  ▾ US-2 … (tiroir: chat + LLM calls)     │   │   │
│ │                    └──────────────────────────────────────────┘   │   │
│ └───────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
```

### Activity (composant exporté)

**Props** (`interface Props`) :

| Prop | Type | Oblig. |
|---|---|---|
| `epics` | `Epic[]` | oui (mais `void epics` — non utilisée) |
| `stories` | `UserStory[]` | oui |
| `streams` | `Stream[]` | non |
| `projectId` | `string` | oui |
| `phase` | `string` | non (déclarée mais non consommée dans le corps) |
| `awaitingApproval` | `string` | non — phase en attente de validation |
| `onApprove` | `() => void` | non |
| `onReject` | `() => void` | non |
| `ticks` | `ProjectTicks` | non — heartbeat live du projet |

**State** : `crewFilter: string` (`""` = tous), `crewOpen: boolean` (init true).

**Dérivations (useMemo)** :
- `now = Date.now()` (à chaque rendu), `tickTs = ticks.ts * 1000` si présent.
- `tickById: Map<string, TickItem>` depuis `ticks.items`.
- `storyById`, `taskById` (maps id → objet, tâches aplaties).
- `graph = buildWorkGraph(stories, streams ?? [])`.
- `rows` : pour chaque item du graphe ayant une source →
  `{ item, view: deriveItemView(source, tick), source, blockers: blockedBy(id, graph) }`.
- `counts` : `ticks.counts` si présent, sinon dérivé des rows
  (running = in_progress/red/green ; done ; failed ; blocked si blockers ;
  sinon queued).
- `stallReason = ticks?.stallReason ?? ""` ; `attentionCount = failed + blocked`.
- `crew` : Map persona→count sur les rows, triée alphabétiquement.
- `visibleRows` : filtrées par `crewFilter` ; `attentionRows` =
  `needsAttention` ; `normalRows` = le complément **uniquement si**
  `attentionRows.length > 0` (BUG11 : pas de ligne dupliquée), sinon toutes.
- `sendGuidance(item)` : curried → `taskChat`/`storyChat(projectId, id, message)`.

**DOM** :
```
section.panel.activity [role=region, aria-label=activity.regionAriaLabel « Activité »]
  div.activity-header
    h2 → activity.heading « ⚡ Activité »
    div.activity-counts [data-testid=activity-counts]
      span.count-chip.count-running [title « En cours »]  → « {n} en cours » (countRunning)
      span.count-chip.count-queued  [title « En file »]   → « {n} en file »  (countQueued)
      span.count-chip.count-done    [title « Faits »]     → « {n} faits »    (countDone)
      span.count-chip.count-failed  [title « En échec »]  → « {n} échecs »   (countFailed)
    (si attentionCount>0) span.attention-chip [data-testid=attention-chip,
      title=activity.attentionTitle « Items en échec ou bloqués nécessitant une intervention »]
      → activity.attentionChip « ⚠ {n} à traiter »
    (si stallReason) span.stall-reason [data-testid=stall-reason,
      title=activity.stallTitle « Pourquoi rien ne progresse actuellement »]
      → activity.stall « ⏸ {reason} » (reason via stallLabel)
  (si awaitingApproval)
    div.approval-banner.approval-banner-scene [data-testid=approval-banner-activity, role=alert]
      span.approval-banner-text → activity.approvalRequired « ⏸ Validation requise — » + <strong>{awaitingApproval}</strong>
      (si onApprove) button.small-btn.approve-btn → « ✅ Approuver » (approve)
      (si onReject)  button.small-btn.danger      → « ✋ Rejeter »   (reject)
  div.activity-body
    (si crew non vide)
      div.crew-rail [data-testid=crew-rail]
        button.crew-rail-toggle [aria-expanded, data-testid=crew-rail-toggle]
          → "▾ "/"▸ " + activity.crewToggle « Équipe »   (clic → toggle crewOpen)
        (si crewOpen)
          div.crew-rail-list [role=group, aria-label=activity.crewFilterAriaLabel « Filtre par agent »]
            button[.active][aria-pressed][data-testid=crew-all] → activity.crewAll « Tous »
            button×persona [data-testid=crew-<persona>] → "<icône> <label> ({n})"
              (clic : toggle — re-clic sur le filtre actif le désactive)
    div.activity-rows-wrap
      (si attentionRows non vide)
        div.activity-attention-region [data-testid=attention-region,
          aria-label=activity.attentionRegionAriaLabel « À traiter en priorité »]
          h3.activity-region-title → activity.attentionRegionTitle « À traiter »
          <ActivityRow/>× (rows attention)
      div.activity-rows [data-testid=activity-rows]
        (si visibleRows vide) p.placeholder → activity.empty
          « Aucun item à afficher. L'activité apparaîtra ici pendant le build. »
        (sinon) <ActivityRow/>× (normalRows)
```

### ActivityRow (interne)

**Rôle** : une ligne d'activité — Stepper + menu d'actions par item + tiroir
repliable (chat ciblé, extension de critères pour une US todo, appels LLM).

**Props** : `item: WorkItem`, `view: ItemView`, `source: UserStory | Task |
undefined`, `blockers: string[]`, `now: number`, `tickTs?: number`,
`projectId: string`, `onSendGuidance: (message: string) => Promise<void>`.

**State** : `menuOpen`, `drawerOpen`, `showDiff`, `actionError`, `busy`.

**Logique** : `isTask = item.kind === "task"` ; `persona =
PERSONA_META[view.persona]` ; `attention = needsAttention(view, blockers)` ;
`canExtend` = story existante avec `view.status === "todo"`. `run(fn)` : wrapper
busy + fermeture du menu + capture d'erreur. `handleRetry` →
`rebuildTask`/`rebuildStory` ; `handleForce` → `forceDoneTask`/`forceDoneStory`.

**DOM** :
```
div.activity-row[.activity-row-attention] [data-testid=activity-row-<id>, data-attention]
  div.activity-row-main
    button.activity-row-toggle [aria-expanded=drawerOpen,
      aria-label=activity.detailsAriaLabel « Détails {id} », data-testid=activity-toggle-<id>]
      → "▾"/"▸"                            (clic → toggle tiroir)
    span.activity-row-id → item.id
    (si persona) span.activity-persona [data-testid=activity-persona-<id>,
      title=activity.personaTitle « Agent en cours : {label} »] → "<icône> <label>"
    span.activity-row-title → item.title
    <Stepper view now tickTs/>             (composant externe Stepper.tsx)
    div.activity-row-menu-wrap
      button.ghost.small-btn [aria-haspopup=menu, aria-expanded,
        aria-label=activity.actionsAriaLabel « Actions {id} »,
        data-testid=activity-menu-<id>, disabled=busy] → "⋯"
      (si menuOpen) div.activity-menu [role=menu]
        button[role=menuitem] → activity.menuRetry     « 🔄 Relancer »
        button[role=menuitem] → activity.menuForceDone « ✓ Forcer terminé »
        button[role=menuitem] → activity.menuDiff      « 📊 Diff »       (→ showDiff)
        button[role=menuitem] → activity.menuChat      « 💬 Chat »       (→ ouvre le tiroir)
  (si blockers) div.activity-blockers [data-testid=activity-blockers-<id>]
    → activity.blockedBy « ⛔ bloqué par {blockers} »
  (si actionError) div.edit-error
  (si drawerOpen)
    div.activity-drawer [data-testid=activity-drawer-<id>]
      <ItemChat view guidance=view.guidance onSend=onSendGuidance/>
      (si canExtend) <ExtendCriteria story onExtend=extendStory(projectId, id, criteria)/>
      <LlmActivity projectId itemId=item.id live=isLive(view.status)/>
  (si showDiff)
    div.diff-overlay [data-testid=activity-diff-<id>]  (clic → ferme)
      div.diff-panel (stopPropagation)
        div.diff-header
          span.diff-title → activity.diffTitle « 📊 Diff — {id} »
          button.ghost.diff-close [aria-label « Fermer »] → "✕"
        <DiffContent fetcher=taskDiff|storyDiff/>
```

### ItemChat (interne)

**Rôle** : chat ciblé par item — envoi d'une consigne, liste des consignes avec
statut de livraison. Rendu dans le tiroir d'une ligne.

**Props** : `view: ItemView`, `guidance: GuidanceEntry[]`,
`onSend: (message: string) => Promise<void>`.

**State** : `text`, `busy`, `error`. `submit()` : trim, garde non-vide, appelle
`onSend`, vide le champ ; erreur → `errorMessage`.

**DOM** :
```
div.item-chat [data-testid=item-chat-<viewId>]
  div.item-chat-guidance [data-testid=guidance-list-<viewId>]
    (si vide) p.placeholder.small → activity.noGuidance « Aucune consigne ciblée pour cet item. »
    (sinon) ul.guidance-entries > li.guidance-entry.guidance-<status>
      [data-testid=guidance-entry-<id>, data-status]
      span.guidance-text → g.text
      span.guidance-status.guidance-status-<status> → « en file »/« appliquée »/« trop tard »
  div.item-chat-input
    textarea rows=2 [placeholder=activity.guidancePlaceholder « Consigne ciblée pour {id}… »,
      aria-label « Consigne ciblée pour {id} », data-testid=item-chat-input-<id>]
      (Ctrl+Enter ou Cmd+Enter → submit)
    button.primary.small-btn [disabled=busy||vide, data-testid=item-chat-send-<id>]
      → activity.send « Envoyer »
  (si error) div.edit-error
```

### ExtendCriteria (interne)

**Rôle** : affordance « Étendre les critères » pour une US **todo** (pas encore
construite) : ajoute des critères d'acceptance avant le build.

**Props** : `story: UserStory`, `onExtend: (criteria: string[]) => Promise<void>`.

**State** : `open` (init false), `text`, `busy`, `error`.

**Logique** : `submit()` — découpe le textarea par ligne, trim, filtre vide,
appelle `onExtend([...critères existants (textes), ...ajoutés])`, puis vide et
referme.

**DOM** :
- fermé : `button.ghost.small-btn [data-testid=extend-<storyId>,
  title=activity.extendTitle « Ajouter des critères d'acceptance avant le build »]`
  → `activity.extendButton` « ＋ Étendre les critères ».
- ouvert :
```
div.extend-criteria [data-testid=extend-form-<storyId>]
  textarea rows=3 [placeholder=activity.extendPlaceholder « Un critère par ligne… »,
    aria-label=activity.extendAriaLabel « Nouveaux critères pour {id} »,
    data-testid=extend-input-<storyId>]
  (si error) div.edit-error
  div.edit-actions
    button.primary.small-btn [disabled, data-testid=extend-submit-<storyId>] → common.add « Ajouter »
    button.ghost.small-btn → « Annuler »   (referme + vide)
```

### DiffContent (interne)

**Rôle** : loader de diff minimal (Activity reste autonome ; le Board a
`DiffViewer`, plus riche). Pas de coloration +/-.

**Props** : `fetcher: () => Promise<{ available: boolean; diff: string }>`.

**State/effect** : `loading` (init true), `error`, `diff`, `available` ;
`useEffect []` (fetch unique au montage, flag `cancelled`).

**DOM** : `div.diff-content` → `div.diff-muted` « Chargement… » /
`div.diff-error` / `div.diff-muted` `activity.noDiff` « Aucun diff disponible. »
/ `pre.diff-pre` (diff brut).

---

## RunPanel (`frontend/src/components/RunPanel.tsx`)

**Rôle** : panneau « Exécution » — phase de la pipeline, bannières (erreur,
régressions, livraison, approbation, reprise auto), compteurs de coût, boutons
de contrôle (lancer/pause/stop/reprendre/relancer), menu « Livraison » et zone
de logs repliable avec auto-scroll.

**Props** (`interface Props`, toutes obligatoires) :

| Prop | Type |
|---|---|
| `project` | `ProjectState` |
| `logs` | `LogLine[]` |
| `onRun` | `(args: string) => void` |
| `onStop`, `onPause`, `onResume`, `onStopApp`, `onResumeBuild`, `onRetryFailed`, `onRestartFromScratch`, `onDocument`, `onExportZip`, `onGitExport`, `onCancelResume`, `onApprove`, `onReject`, `onDeploy` | `() => void` |

**Helper module** : `formatTokens(n)` → `"{x.x}k"` si ≥ 1000, sinon la valeur.

**State / refs / effects** :
- `bottomRef: useRef<HTMLDivElement>` — ancre d'auto-scroll des logs.
- `menuOpen: boolean` + `menuRef` — menu overflow « Livraison » (UI7) ;
  `useEffect [menuOpen]` : listener `mousedown` sur `document` fermant le menu
  au clic extérieur (cleanup au démontage/fermeture).
- `runArgs: string` — arguments CLI optionnels transmis à l'app générée.
- `logsOpen: boolean` (init true, UI4) ; `hasLogs = logs.length > 0` ;
  `logsExpanded = logsOpen && hasLogs`.
- `useEffect [logs.length, logsExpanded]` : si déplié,
  `bottomRef.current?.scrollIntoView({ behavior: "smooth" })` (auto-scroll).

**Dérivations** :
- `PHASE_LABEL` construit dans le rendu (re-traduction au changement de langue) :
  `idle`→« En attente », `spec`→« 📋 Spécification (PM) », `analyze`→« 🔍
  Exploration backlog (Analyste) », `architect`→« 🏛️ Architecture (design) »,
  `plan`→« 🏃 Planification (PO) », `build`→« 💻 Développement BDD/TDD »,
  `done`→« ✅ Itération terminée », `stopped`→« ⏹ Arrêté »,
  `needs_attention`→« ⛔ À reprendre », `error`→« 💥 Erreur ».
- `canRun` = phase ∉ `["spec","plan","analyze","architect","build","idle"]`.
- `loopActive` = phase ∉ `["done","stopped","needs_attention","error"]`.
- `showResumeBuild = canResumeBuild(project)` (work.ts, logique partagée avec
  ProjectBar).
- `effStatuses` = statut effectif par story (`effectiveStatus`, work.ts).
- `failedCount` ; `canRetryFailed` = phase dormante
  (`done|stopped|needs_attention|error`) && failedCount > 0.
- `canRestart` = phase dormante && `project.brief` non vide (destructif,
  confirmation côté App).
- Usage : `agentCalls`, `costUsd`, `totalTokens` (in+out), `budgetUsd`,
  `overBudget = budget>0 && cost>=budget`.
- Prévision O2 : `forecastUsd = (costUsd / doneCount) * pendingCount` si
  doneCount>0 et cost>0 (pending = `todo|red|in_progress|green`).

**Diagramme** :

```
┌─ .panel.run[.run-collapsed] ────────────────────────────────────────────┐
│ ┌ .run-header ─────────────────────────────────────────────────────┐   │
│ │ h2 "Exécution"  [phase 💻 Développement BDD/TDD — itération 2 ⏸] │   │
│ │ [⚠️ erreur] [⚠️ n régression(s)] [⛔ Livraison · n]               │   │
│ │ [⏸ Validation requise (phase) ✅ ✋] [⏰ Reprise auto à HH:MM ✕]  │   │
│ │ [💸 $0.1234 / $2.00 · 12.3k tokens · 5 appels] [📈 ~$x / n]       │   │
│ │ ┌ .run-buttons ────────────────────────────────────────────────┐ │   │
│ │ │ [input args] [▶ Lancer le projet] [▶ Continuer le build]     │ │   │
│ │ │ [🔄 Relancer les échecs (n)] [♻️ Relancer from scratch]      │ │   │
│ │ │ [■ Arrêter l'app] [⏸ Pause|▶ Reprendre] [⏹ Stopper]          │ │   │
│ │ │ [⋯ Livraison ▾ → 📘 Doc / ⬇ zip / 🔀 git / 🚀 déploiement]   │ │   │
│ │ └──────────────────────────────────────────────────────────────┘ │   │
│ └──────────────────────────────────────────────────────────────────┘   │
│ .logs-bar  [▾ Logs (42)]                                                │
│ .logs  [source] ligne …  (auto-scroll bas)                              │
└─────────────────────────────────────────────────────────────────────────┘
```

**Structure DOM** :
```
div.panel.run[.run-collapsed si logs repliés]
  div.run-header
    h2 → runPanel.title « Exécution »
    span.phase.phase-<phase>
      → "<PHASE_LABEL> — " + runPanel.iteration « itération {n} »
        + (paused ? runPanel.paused « ⏸ en pause »
           : auto_spec && loopActive ? runPanel.autoSpecLoop « (boucle auto-spec) » : "")
    (si phase==="error") span.run-error [title=runPanel.errorTitle « Détail de l'erreur de la pipeline »]
      → "⚠️ " + (project.error || runPanel.errorNoDetail « Erreur sans détail (voir les logs / le chat). »)
    (si regressions) span.regression-banner [title=runPanel.regressionTitle
      « Des tests précédemment verts ont été cassés »] → runPanel.regressionCount « ⚠️ {n} régression(s) »
    (si delivery_issues) span.run-error [title=issues join "\n"] → "⛔ Livraison · {n}"   (libellé en dur)
    (si awaiting_approval) span.approval-banner [title=runPanel.approvalTitle « Validation requise avant le build »]
      → runPanel.approvalRequired « ⏸ Validation requise ({phase}) »
      + button.small-btn.approve-btn → « ✅ Approuver »  (onApprove)
      + button.small-btn.danger      → « ✋ Rejeter »    (onReject)
    (si resume_at>0) span.resume-banner [title=runPanel.resumeTitle « Fenêtre d'usage Claude épuisée :
      le travail reprendra automatiquement »]
      → runPanel.resumeAt « ⏰ Reprise auto à » + heure locale fr-FR HH:MM
      + button.small-btn [title=runPanel.cancelAutoResume « Annuler la reprise automatique »] → "✕"  (onCancelResume)
    (si agentCalls>0) span.usage-meter[.over-budget]
      → "💸 $<cost 4 déc.>[ / $<budget 2 déc.>] · <tokens formatés> tokens · <n> appels"
    (si pendingCount>0 && forecastUsd>0) span.forecast-meter [title=runPanel.forecastTitle
      « Estimation du coût restant (historique coût/story du projet) »]
      → runPanel.forecast « 📈 ~${cost} / {n} story(ies) »
    div.run-buttons
      (si canRun && !running) input.run-args [type=text,
        placeholder=runPanel.argsPlaceholder « arguments (ex. auth-screen)… »,
        title=runPanel.argsTitle « Arguments CLI passés à l'application générée (optionnel) »]
        (Enter → onRun(runArgs.trim()))
      button.primary [disabled=!canRun||running] → running ? « ▶ En cours… » : « ▶ Lancer le projet »
      (si showResumeBuild) button.primary [title=runPanel.resumeBuildTitle « Reprendre la phase build
        sur les stories restantes »] → « ▶ Continuer le build »  (onResumeBuild)
      (si canRetryFailed) button.action-btn [title=runPanel.retryFailedTitle « Réinitialiser et relancer
        toutes les user stories en échec »] → « 🔄 Relancer les échecs ({n}) »  (onRetryFailed)
      (si canRestart) button.action-btn.danger [title=runPanel.restartScratchTitle « Tout effacer (code,
        epics, stories) SAUF le brief initial, puis relancer la planification PO et le build complet »]
        → « ♻️ Relancer from scratch »  (onRestartFromScratch)
      (si running) button.danger [title=runPanel.stopAppTitle « Arrêter l'application générée »]
        → « ■ Arrêter l'app »  (onStopApp)
      (si loopActive) paused ? button → « ▶ Reprendre » [title « Reprendre la pipeline »] (onResume)
                              : button → « ⏸ Pause » [title « Mettre la pipeline en pause »] (onPause)
      (si loopActive || auto_spec) button.danger [disabled=!loopActive] → « ⏹ Stopper »  (onStop)
      (si canRun) div.run-menu-wrap [ref=menuRef]
        button.ghost [aria-haspopup=menu, aria-expanded, title=runPanel.deliveryTitle
          « Livraison & export du produit généré »] → « ⋯ Livraison »
        (si menuOpen) div.run-menu [role=menu]
          button[role=menuitem] → « 📘 Doc (README) »     (onDocument)
          button[role=menuitem] → « ⬇ Exporter en zip »   (onExportZip)
          button[role=menuitem] → « 🔀 Commit git »        (onGitExport)
          button[role=menuitem] → « 🚀 Déploiement »       (onDeploy)
          (chaque item ferme le menu avant d'appeler le callback)
  div.logs-bar
    button.logs-toggle [disabled=!hasLogs,
      title = hasLogs ? runPanel.logsToggleTitle « Afficher / masquer les logs »
                      : runPanel.logsEmptyTitle « Les logs apparaîtront ici pendant l'exécution »]
      → hasLogs ? "▾/▸ " + runPanel.logsCount « Logs ({n}) » : runPanel.logsEmpty « Logs — aucun pour l'instant »
  (si logsExpanded) div.logs
    div.log-line ×N → span.log-source "[{source}]" + " " + ligne
    div [ref=bottomRef]   (ancre d'auto-scroll)
```

---

## LlmActivity (`frontend/src/components/LlmActivity.tsx`)

### LlmActivity (composant exporté)

**Rôle** (O2) : vue intégrée (jamais une popup — rendu inline) des derniers
prompts/réponses LLM d'un work item. Utilisée dans le tiroir d'une ligne
Activity et dans les détails story/task du Board. **Polling toutes les 3 s**
(`POLL_MS = 3000`) quand `live` ; fetch unique sinon (historique).

**Props** : `projectId: string` (oblig.), `itemId: string` (oblig.),
`live?: boolean` (défaut `false`), `limit?: number` (défaut `20`).

**State / effects** :
- `items: AgentInteraction[] | null` (null = chargement initial), `error: string`,
  `now: number` (init `Date.now()`).
- `load` (useCallback [projectId, itemId, limit]) :
  `getItemInteractions(projectId, itemId, limit)` ; un échec (p. ex. 404 — pas
  d'historique) est silencieux : `setItems(cur => cur ?? [])`.
- `useEffect [load, live]` : `load()` au montage ; si `live`, `setInterval`
  3 s qui met à jour `now` **et** recharge ; cleanup `clearInterval`.

**Dérivation** : `ordered = [...items].reverse()` (le plus récent d'abord) ;
`firstId = ordered[0]?.id` — la carte la plus récente s'auto-ouvre
(`defaultOpen` ne s'applique qu'au montage, donc un nouvel appel arrivant en
polling s'ouvre sans perturber les cartes déjà togglées).

Constantes de module :
- `ROLE_META` (icône + clé i18n) : `dev: 👨‍💻 « Dev »`, `dev-frontend: 🎨
  « Dev front »`, `qa: 🧪 « QA »`, `critic: 🔍 « Critique »`, `judge: ⚖️
  « Juge »`, `architect: 🏛️ « Architecte »`, `analyst: 📊 « Analyste »`,
  `pm: 📋 « PM »`, `sm: 🗂 « PO/SM »`, `tech-writer: 📝 « Rédacteur »`,
  `evaluator: 🕵️ « Évaluateur »`, `security-reviewer: 🛡️ « Sécurité »`,
  `retro: 🔄 « Rétro »`.
- `roleMeta(persona, phase, t)` : persona inconnue → icône `🤖` + label =
  persona, ou phase sans le préfixe `phase:`, ou `"agent"`.
- `timeAgo(ts, now, t)` : « il y a {s}s » (<60 s), « il y a {m} min » (<60 min),
  « il y a {h} h » (clés `llmActivity.timeAgoSeconds/Minutes/Hours`).
- `tokens(it)` : `"{in} in / {out} out"` (via `toLocaleString`, parties omises
  si nulles).

**DOM** :
```
(chargement) div.llm-activity.llm-muted [data-testid=llm-activity-<itemId>] → « Chargement… »
(sinon)
div.llm-activity [data-testid=llm-activity-<itemId>]
  div.llm-activity-head
    span.llm-activity-title → llmActivity.title « 🧠 Appels LLM »
    (si live) span.llm-live [title=llmActivity.liveTitle « Mise à jour en direct »] → « ● live »
    span.llm-activity-count → items.length
  (si error) div.edit-error
  (si vide) p.placeholder.small
    → live ? emptyLive « Aucun appel pour l'instant — ils apparaîtront ici dès que l'agent
       travaille sur cet item. » : emptyHistory « Aucun appel LLM enregistré pour cet item. »
  (sinon) div.llm-call-list > <InteractionCard/>×N (defaultOpen sur la 1re)
```

### InteractionCard (interne)

**Rôle** : un aller-retour LLM capturé — replié = ligne d'entête ; déplié =
prompt + réponse (+ erreur).

**Props** : `it: AgentInteraction` (oblig.), `now: number` (oblig.),
`defaultOpen: boolean` (oblig.).

**State** : `open` (init `defaultOpen`).

**DOM** :
```
div.llm-call[.llm-call-error si !it.ok] [data-testid=llm-call-<id>]
  button.llm-call-head [aria-expanded, data-testid=llm-call-head-<id>]  (clic → toggle)
    span.llm-call-caret → "▾"/"▸"
    span.llm-call-role [title=label] → "<icône> <label>"
    (si !ok) span.llm-call-badge.llm-call-badge-error → llmActivity.badgeError « échec »
    (si tokens) span.llm-call-tokens → "1,234 in / 567 out"
    (si cost_usd>0) span.llm-call-cost → "$<4 déc.>"
    (si duration_ms>0) span.llm-call-dur → "<s, 1 déc.>s"
    span.llm-call-time → timeAgo (« il y a {s}s »…)
  (si open) div.llm-call-body
    (si !ok && error) div.llm-call-section > h6 « Erreur » (errorHeading) + pre.llm-pre.llm-pre-error
    div.llm-call-section
      h6 → « Prompt » (promptHeading) + (si prompt_truncated) span.llm-trunc « (tronqué) » (truncated)
      pre.llm-pre → it.prompt || « (vide) » (empty)
    (si response || ok) div.llm-call-section
      h6 → « Réponse » (responseHeading) + (si response_truncated) span.llm-trunc « (tronqué) »
      pre.llm-pre → it.response || « (vide) »
```

---

## ProjectBar (`frontend/src/components/ProjectBar.tsx`)

**Rôle** : barre horizontale de sélection/gestion des projets en haut de l'app :
sélecteur `<select>` 🗂, chips des projets actifs (+ projet courant), boutons
▶/⏹/📦/↩/✕, bouton « ＋ Nouveau » et toggle des archivés.

**Props** (`interface Props`, toutes obligatoires) :

| Prop | Type |
|---|---|
| `projects` | `ProjectState[]` |
| `selectedId` | `string \| null` |
| `onSelect` | `(id: string) => void` |
| `onNew` | `() => void` |
| `onDelete`, `onArchive`, `onUnarchive`, `onPlay`, `onStop` | `(project: ProjectState) => void` |
| `showArchived` | `boolean` |
| `onToggleArchived` | `() => void` |

**Constantes de module** :
- `PHASE_DOT` (couleur hexadécimale de la pastille par phase) :
  `idle: #8a93a6`, `spec: #ffb454`, `analyze: #b07cff`, `plan: #b07cff`,
  `architect: #39c5bb`, `build: #4f8cff`, `done: #3ecf8e`, `stopped: #8a93a6`,
  `needs_attention: #ffb454`, `error: #ff5c6c`. Fallback `#8a93a6`.
- `ACTIVE_PHASES = ["spec","analyze","plan","architect","build"]` (chip qui
  pulse + bouton ⏹).
- `PHASE_BADGE` (émoji texte des `<option>`) : `idle ⚪`, `spec 🟠`, `analyze 🟣`,
  `plan 🟣`, `architect 🟢`, `build 🔵`, `done 🟢`, `stopped ⚪`,
  `needs_attention 🟠`, `error 🔴`. Un projet en pause affiche `⏸`.

**Helpers module** :
- `progress(p)` : `{ done, total } | null` (null si aucune story) —
  done = stories `status === "done"` (statut **stocké**, pas effectif).
- `statusRank(p)` (ordre UI3) : actif non-pausé → 0, actif pausé → 1,
  `stopped|needs_attention|error` → 2, `done` → 3, sinon 4.

**Dérivations dans le rendu** :
- `optionLabel(p)` : « `<badge> <nom>` · `<done>/<total>` · `<phase>` [· archivé] »
  — badge = `⏸` si pausé sinon `PHASE_BADGE` ; la phase pausée utilise
  `projectBar.phasePaused` « {phase} (pause) » ; `projectBar.archived`
  « archivé ».
- `archivedCount` ; `visible` = tous ou non-archivés selon `showArchived`.
- `sorted` = `visible` trié par `statusRank`.
- `selectable` = `sorted`, avec le projet sélectionné préfixé s'il n'y figure
  pas (archivé/masqué).
- `chipProjects` = projets en phase active **ou** projet courant (UI3 : fini
  l'overflow) ; `hiddenFromChips = visible.length - chipProjects.length`.
- Par chip : `active` (phase active), `working = active && !paused`,
  `canPlay = (active && paused) || canResumeBuild(p)` (work.ts).

**Structure DOM** :
```
div.project-bar
  (si selectable non vide)
    label.project-select [title=projectBar.selectActiveProject « Sélectionner le projet actif »]
      span.project-select-icon [aria-hidden] → "🗂"
      select [aria-label idem, value=selectedId ?? "", onChange → onSelect]
        option[value="" disabled hidden] → projectBar.chooseProject « — Choisir un projet ({count}) — »
        option×N → optionLabel(p)   (ex. « 🔵 Mon appli · 2/3 · build »)
  (chips) div.project-chip[.active si sélectionné][.archived] ×N   (clic → onSelect(p.id))
    span.dot[.pulse si working] [style background=PHASE_DOT[phase],
      title = paused ? projectBar.phasePausedDot « {phase} (en pause) » : phase]
    span.chip-name → p.name
    (si prog) span.chip-progress [title=projectBar.progressTitle
      « {done} story(ies) terminée(s) sur {total} »] → "{done}/{total}"
    (si working) button.chip-play [title=projectBar.stopPipeline
      « Stopper la pipeline de ce projet »] → "⏹"   (stopPropagation + onStop(p))
    (si canPlay) button.chip-play [title = paused ? projectBar.resumePipeline « Reprendre la pipeline »
      : projectBar.resumeBuild « Reprendre le build des stories restantes »] → "▶"  (stopPropagation + onPlay(p))
    (si archived) button.chip-archive [title=projectBar.unarchiveProject « Désarchiver le projet »]
      → "↩"   (stopPropagation + onUnarchive(p))
    (sinon)      button.chip-archive [title=projectBar.archiveProject « Archiver le projet »]
      → "📦"  (stopPropagation + onArchive(p))
    button.chip-del [title=projectBar.deleteProject « Supprimer le projet »]
      → "✕"   (stopPropagation + onDelete(p))
  (si hiddenFromChips>0) span.chips-hint [title=projectBar.inactiveHint
    « Projets inactifs — accessibles via le sélecteur 🗂 »]
    → projectBar.hiddenCount « +{count} dans 🗂 »
  button.project-new → projectBar.new « ＋ Nouveau »   (onNew)
  (si archivedCount>0) button.archived-toggle[.active si showArchived]
    [title = showArchived ? « Masquer les projets archivés » : « Afficher les projets archivés »]
    → projectBar.archivedToggle « 📦 Archivés ({count}) »   (onToggleArchived)
```

**Interactions** : tout bouton interne à une chip fait `e.stopPropagation()`
pour ne pas sélectionner le projet ; le clic sur la chip elle-même sélectionne.
Pas de state local ni d'effect (composant purement dérivé des props).

---

## Annexe — dépendances transverses

- **`types.ts`** fournit les helpers de dérivation partagés :
  `usEffectiveStatus`, `criterionState`, `mergeState`, `blockedBy` (variante
  Board : `(dependsOn, status, stories)`).
- **`work.ts`** (non documenté ici) fournit `buildWorkGraph`, `deriveItemView`,
  `blockedBy(id, graph)` (variante Activity), `canResumeBuild`,
  `effectiveStatus` — partagés entre Activity, RunPanel et ProjectBar.
- **`Stepper.tsx`** est un composant externe rendu par `ActivityRow`
  (`<Stepper view now tickTs/>`, data-testid `stepper-<id>`).
- **`api.ts`** : appels utilisés — `addStory`, `deleteStory`, `editStory`,
  `extendStory`, `forceDoneStory`, `forceDoneTask`, `rebuildStory`,
  `rebuildTask`, `reorderStories`, `splitItem`, `storyDiff`, `taskDiff`,
  `storyChat`, `taskChat`, `getItemInteractions`, `errorMessage`.
