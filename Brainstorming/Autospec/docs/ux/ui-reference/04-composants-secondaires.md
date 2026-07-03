# 04 — Composants secondaires du frontend Autospec

Référence exhaustive des composants « secondaires » de `frontend/src/components/` (React 18 + TypeScript), destinée à permettre la **recréation à l'identique** de l'UI. Les libellés cités sont ceux de la locale **FR** (`frontend/src/i18n/messages/*.ts`) ; la mécanique i18n (`useI18n`, `t(key, vars)`, interpolation `{name}`) est décrite dans `frontend/src/i18n/i18n.ts` (fallback : langue courante → anglais → la clé elle-même).

Conventions de ce document :
- Les arbres DOM sont indiqués avec les **classes CSS exactes** ; `[cond]` = rendu conditionnel ; les émojis/SVG sont reproduits verbatim.
- « App » désigne `frontend/src/App.tsx`, qui rend la plupart de ces composants dans `main.workspace` → `div.col-left` (panneaux latéraux) et `div.col-right` (vues de travail).

---

## WorkspaceViews

**Fichier** : `frontend/src/components/WorkspaceViews.tsx`

### Rôle et emplacement
Conteneur des « lentilles » sur le même produit, rendu par App dans `div.col-right` (au-dessus de `RunPanel` et `CodeViewer`). Il coordonne quatre vues : **Activité** (`Activity`), **Vision produit** (`Board`), **Graphe** (`DepGraphPanel`) et **Itérations** (`IterationsView`), avec des liens croisés (une pastille « it. N » du Board ouvre la chronologie sur N ; un chip de la chronologie renvoie au Board navigué dessus).

### Props
| Prop | Type | Oblig. |
|---|---|---|
| `epics` | `Epic[]` | oui |
| `stories` | `UserStory[]` | oui |
| `streams` | `Stream[]` | non (ST-12 ; vide/absent = projet legacy mono-stream) |
| `projectId` | `string` | oui |
| `phase` | `string` | non |
| `iterationUsage` | `Record<string, Usage>` | non (coût/tokens par itération, clé = n° en string) |
| `onRollbackTo` | `(iter: number) => void` | non (confirmation + toast gérés côté App) |
| `ticks` | `ProjectTicks` | non (heartbeat B-UX du projet ; absent hors BUILD) |
| `awaitingApproval` | `string` | non (P13 : gate d'approbation, vide = pas de gate) |
| `onApprove` | `() => void` | non |
| `onReject` | `() => void` | non |

### State, refs, effects
- `view: "vision" | "iterations" | "activity" | "graph"` — vue active. **Valeur initiale** : `"activity"` si `phase === "build"`, sinon `"vision"`.
- `boardFocus: { epicId: string; storyId?: string } | null` — cible de navigation transmise au Board (prop `focus`, consommée via `onFocusConsumed` → remise à `null`).
- `iterFocus: number | null` — itération à mettre en évidence dans IterationsView.
- `snapshotIters: number[]` — itérations disposant d'un snapshot git (donc « rollback-ables »).
- `useMemo iterCount` : `new Set(epics.map(e => e.iteration)).size` ; `multiIter = iterCount > 1`.
- `useMemo hasGraph` : vrai si au moins une story a `tasks.length > 0` ou `depends_on.length > 0` (une liste plate d'US indépendantes n'a rien à montrer).
- **Effect** (deps `[projectId, iterCount, onRollbackTo]`) : si `onRollbackTo` fourni, appelle `getIterations(projectId)` (GET `/api/projects/{id}/iterations`) et stocke le résultat dans `snapshotIters` (`[]` en cas d'erreur) ; flag `cancelled` pour ignorer les résultats après démontage.

### Logique de gating
- `showIterations = view === "iterations" && multiIter` — l'onglet Itérations n'existe qu'à partir de **2 itérations** ; si la vue active est « iterations » mais que ce n'est plus vrai, retombe sur la vision.
- `showGraph = view === "graph" && hasGraph` — même principe pour le Graphe.
- L'onglet « Vision produit » est sélectionné quand aucune des trois autres vues n'est affichée.

### Structure DOM
```
<> (fragment)
├─ div.view-toggle [role="tablist"] [aria-label="Vue du projet"]
│  ├─ button [role="tab"] [aria-selected] (.active si vue active) → "⚡ Activité"
│  ├─ button [role="tab"] → "🗂 Vision produit"
│  ├─ [hasGraph] button [role="tab"] → "🔗 Graphe"
│  └─ [multiIter] button [role="tab"] → "🕒 Itérations"
└─ (une seule des 4 vues)
   ├─ [showGraph]      <DepGraphPanel stories streams onOpenItem={openWorkItemStory}/>
   ├─ [showActivity]   <Activity epics stories streams projectId phase awaitingApproval onApprove onReject ticks/>
   ├─ [showIterations] <IterationsView epics stories focusIter={iterFocus} iterationUsage rollbackableIters={snapshotIters} onRollbackTo onOpenEpic onOpenStory/>
   └─ [sinon]          <Board epics stories streams projectId phase focus={boardFocus} onFocusConsumed onOpenIteration={multiIter ? openIteration : undefined}/>
```

### Interactions / callbacks
- Clic sur un onglet → `setView(...)`.
- `openIteration(iter)` : `setIterFocus(iter)` + `setView("iterations")` (fourni au Board seulement si `multiIter`).
- `openStory(epicId, storyId)` : `setBoardFocus({epicId, storyId})` + `setView("vision")`.
- `openEpic(epicId)` : `setBoardFocus({epicId})` + `setView("vision")`.
- `openWorkItemStory(storyId)` : retrouve la story dans `stories` (nœud de graphe → sa story/TS conteneuse) puis `openStory(s.epic_id, s.id)`.

### i18n (namespace `workspaceViews`)
| Clé | FR |
|---|---|
| `workspaceViews.projectView` | Vue du projet |
| `workspaceViews.activity` | ⚡ Activité |
| `workspaceViews.productVision` | 🗂 Vision produit |
| `workspaceViews.iterations` | 🕒 Itérations |
| `workspaceViews.graph` | 🔗 Graphe |

### Diagramme
```
┌──────────────────────────────────────────────────────────────┐
│ view-toggle : [⚡ Activité][🗂 Vision produit][🔗 Graphe][🕒 Itérations]
├──────────────────────────────────────────────────────────────┤
│                                                              │
│   Activity ── ou ── Board ── ou ── DepGraphPanel ── ou ──    │
│                       ▲                    │      Iterations │
│                       │ openStory/openEpic │        View     │
│                       └────────────────────┘          │      │
│        Board ── pastille « it. N » ──► openIteration ──┘     │
└──────────────────────────────────────────────────────────────┘
```

---

## IterationsView

**Fichier** : `frontend/src/components/IterationsView.tsx`

### Rôle et emplacement
Vue chronologique du build : **une section par itération** (la plus récente en haut), rendue par `WorkspaceViews` quand l'onglet « 🕒 Itérations » est actif. Pendant temporel de la pastille « it. N » du Board (lien bidirectionnel). Réutilise `epicProgress` et `EpicProgressBar` importés de `./Board`.

### Sous-fonction interne : `formatTokens(n: number): string`
`n >= 1000` → `` `${(n/1000).toFixed(1)}k` `` (ex. `12.3k`), sinon `String(n)`.

### Props
| Prop | Type | Oblig. |
|---|---|---|
| `epics` | `Epic[]` | oui |
| `stories` | `UserStory[]` | oui |
| `focusIter` | `number \| null` | non (itération à mettre en évidence + scroller) |
| `iterationUsage` | `Record<string, Usage>` | non |
| `rollbackableIters` | `number[]` | non (itérations avec snapshot → bouton rollback affiché) |
| `onRollbackTo` | `(iter: number) => void` | non |
| `onOpenEpic` | `(epicId: string) => void` | oui |
| `onOpenStory` | `(epicId: string, storyId: string) => void` | oui |

### State, refs, effects
- Pas de state local.
- `focusRef: useRef<HTMLElement | null>` — attaché à la `<section>` de l'itération focus.
- **Effect** (deps `[focusIter]`) : `focusRef.current?.scrollIntoView?.({behavior: "smooth", block: "start"})` — le `?.` sur la méthode protège jsdom (tests) où `scrollIntoView` n'existe pas.

### Logique
- `iters = [...new Set(epics.map(e => e.iteration))].sort((a,b) => b - a)` — n° d'itérations **décroissants**.
- Pour chaque itération `n` : `iterEpics` (epics de l'itération), `iterStories` (stories de l'itération), `prog = epicProgress(iterStories)` (compte par **statut effectif** ; `state` ∈ `working | failed | done | pending`), `focused = n === focusIter`, `usage = iterationUsage?.[String(n)]`, `canRollback = !!onRollbackTo && (rollbackableIters ?? []).includes(n)`.
- Tables de libellés construites via `t()` :
  - `STATUS_LABEL` (statuts de story) : `todo`→« À faire », `in_progress`→« Dev en cours », `red`→« Tests rouges », `green`→« Tests verts », `done`→« Terminé », `failed`→« Échec ».
  - `STATE_LABEL` (état d'itération) : `working`→« ● en cours », `done`→« ✓ livrée », `failed`→« ⚠ en échec », `pending`→« à faire ».

### Structure DOM
```
div.panel.iterations
├─ div.board-top
│  ├─ h2 → "🕒 Itérations"
│  └─ span.iter-hint → "Chronologie du build — clic sur un élément pour l'ouvrir dans la vision produit"
└─ div.iter-timeline
   └─ (pour chaque itération n, décroissant)
      section.iter-card.epic-{prog.state}[.focused] [data-testid="iter-card-{n}"] [ref si focus]
      ├─ header.iter-card-head
      │  ├─ span.iter-num
      │  │  ├─ [prog.state==="working"] span.spinner.spinner-sm [aria-hidden="true"]
      │  │  └─ "Itération {n}"
      │  ├─ span.iter-state.state-{prog.state} → STATE_LABEL[state]
      │  └─ span.iter-counts → "{epics} épic(s) · {done}/{total} US"
      ├─ <EpicProgressBar prog={prog}/>   (div.epic-progress[role=progressbar] + div.epic-progress-fill.state-{state} ; ligne div.epic-card-meta)
      ├─ [usage] div.iter-usage [title="Coût et tokens consommés durant cette itération"]
      │           → "💰 ${cost_usd.toFixed(4)} · 🔢 {formatTokens(input+output)} tok · {calls} appel(s) agent"
      ├─ [iterEpics.length>0] div.iter-epics
      │  └─ button.iter-epic-chip [title="Ouvrir l'epic {id} dans la vision produit"] → "{e.id} · {e.title}"
      ├─ [iterStories.length>0] ul.iter-stories
      │  └─ li → button.iter-story-chip.status-{s.status} [title="Ouvrir {id} dans la vision produit"]
      │     ├─ span.iter-story-id → s.id
      │     ├─ span.iter-story-title → s.title
      │     └─ span.badge.badge-{s.status} → STATUS_LABEL[s.status]
      │  [sinon] p.placeholder.small → "Aucune user story dans cette itération."
      └─ [canRollback] div.iter-card-actions
         └─ button.ghost.small-btn [title="Restaurer le workspace au snapshot de l'itération {n}"]
            → "↩ Revenir à cette itération"
```

### Interactions
- Chip epic → `onOpenEpic(e.id)` ; chip story → `onOpenStory(s.epic_id, s.id)` (retour au Board navigué).
- Bouton rollback → `onRollbackTo!(n)` (App gère la confirmation et le toast).

### i18n (namespace `iterationsView`)
| Clé | FR |
|---|---|
| `title` | 🕒 Itérations |
| `hint` | Chronologie du build — clic sur un élément pour l'ouvrir dans la vision produit |
| `iteration` | Itération {n} |
| `countsOne` / `countsMany` | {epics} épic · {done}/{total} US / {epics} épics · {done}/{total} US |
| `usageTitle` | Coût et tokens consommés durant cette itération |
| `usageOne` / `usageMany` | {calls} appel agent / {calls} appels agent |
| `openEpicTitle` | Ouvrir l'epic {id} dans la vision produit |
| `openStoryTitle` | Ouvrir {id} dans la vision produit |
| `noStories` | Aucune user story dans cette itération. |
| `rollbackTitle` | Restaurer le workspace au snapshot de l'itération {n} |
| `rollbackButton` | ↩ Revenir à cette itération |
| `statusTodo`…`statusFailed` | À faire / Dev en cours / Tests rouges / Tests verts / Terminé / Échec |
| `stateWorking`/`stateDone`/`stateFailed`/`statePending` | ● en cours / ✓ livrée / ⚠ en échec / à faire |

### Diagramme
```
🕒 Itérations           Chronologie du build — clic…
┌─ Itération 3 ──── ● en cours ─── 2 épics · 1/4 US ─┐
│ ▓▓▓▓▓░░░░░░░░ (EpicProgressBar)                    │
│ 💰 $0.1234 · 🔢 45.2k tok · 12 appels agent        │
│ [EP-5 · Titre] [EP-6 · Titre]        (chips epics) │
│ • US-9  Titre   [Dev en cours]     (chips stories) │
│ [↩ Revenir à cette itération]                      │
└────────────────────────────────────────────────────┘
┌─ Itération 2 ──── ✓ livrée … ───────────────────────┐
│ …                                                   │
└────────────────────────────────────────────────────┘
```

---

## ChatPanel

**Fichier** : `frontend/src/components/ChatPanel.tsx`

### Rôle et emplacement
Panneau de conversation « Chat — spécification & feedback », premier panneau de `div.col-left` dans App. Affiche l'historique des messages multi-rôles (user/PM/PO/Dev/…), le sélecteur de mode de spec (interview/brainstorming) pendant la phase `spec`, l'offre de brainstorming (B-IDEA) et la zone de saisie.

### Props (interface `Props`)
| Prop | Type | Oblig. |
|---|---|---|
| `chat` | `ChatMessage[]` (`{role: ChatRole; content: string; ts: number}`) | oui |
| `phase` | `PipelinePhase` | oui |
| `onSend` | `(message: string) => void` | oui |
| `specMode` | `"interview" \| "brainstorm"` | oui |
| `onSetSpecMode` | `(mode: "interview" \| "brainstorm") => void` | oui |
| `awaitingBrainstorm` | `boolean` | non (défaut `false`) |
| `brainstormTechniques` | `string[]` | non (défaut `[]`) |
| `onResolveBrainstorm` | `(accept: boolean) => void` | non |

### State, refs, effects
- `draft: string` — brouillon du message.
- `bottomRef: useRef<HTMLDivElement>` — ancre en fin de liste.
- **Effect** (deps `[chat.length]`) : `bottomRef.current?.scrollIntoView({behavior: "smooth"})` — auto-scroll vers le bas à chaque nouveau message.

### Logique
- `ROLE_LABEL` : `user`→« Toi », `pm`→« 📋 PM », `po`→« 🏃 PO », `dev`→« 💻 Dev », `analyst`→« 🔍 Analyste », `architect`→« 🏛️ Architecte », `qa`→« 🧪 QA », `critic`→« 🧐 Critique », `judge`→« ⚖️ Juge », `system`→« ⚙️ Système ». Fallback : rôle brut.
- `send()` : trim du draft ; si vide → return ; sinon `onSend(message)` puis `setDraft("")`.
- `placeholder` du textarea selon la phase : `spec` → « Réponds au PM… » ; `build`/`architect` → « Donne une consigne au dev en cours… (prise en compte aux prochaines tentatives) » ; sinon → « Donne ton feedback sur l'itération en cours… ».

### Structure DOM
```
div.panel.chat
├─ div.chat-header
│  ├─ h2 → "Chat — spécification & feedback"
│  └─ [phase==="spec"] div.spec-mode-switch [role="group"] [aria-label="Mode de spécification"]
│     ├─ button.spec-mode-btn[.active] [aria-pressed] [title="Interview socratique : clarifier le besoin par une série de questions ciblées, dimension par dimension."] → "💬 Interview"
│     └─ button.spec-mode-btn[.active] [aria-pressed] [title="Brainstorming : le PM/analyste re-questionne lui-même le besoin (divergence puis convergence)."] → "🧠 Brainstorming"
├─ div.chat-messages
│  ├─ [chat vide] div.chat-empty → p.placeholder
│  │     phase spec  → "Le PM va te poser des questions pour cadrer le besoin — réponds ci-dessous."
│  │     sinon       → "Les échanges PM → PO → QA → Dev s'afficheront ici. Tu peux aussi envoyer un feedback à tout moment."
│  ├─ [sinon, pour chaque message m (clé = index)] div.msg.msg-{m.role}
│  │  ├─ span.msg-role → ROLE_LABEL[m.role] ?? m.role
│  │  └─ pre → m.content
│  └─ div [ref=bottomRef]     (ancre d'auto-scroll)
├─ [awaitingBrainstorm && onResolveBrainstorm] div.brainstorm-offer [role="group"] [aria-label="Proposition de brainstorming"]
│  ├─ p → "💡 Ton idée est encore ouverte. Une session de " <strong>brainstorming</strong> " pour l'affiner ?"
│  │  └─ [techniques non vides] span.brainstorm-tech → " Techniques : {list}."   (list = join(", "))
│  └─ div.brainstorm-actions
│     ├─ button.brainstorm-btn.accept → "🧠 Oui, on explore ensemble"
│     └─ button.brainstorm-btn.refuse → "🤖 Non, affine en autonomie"
└─ div.chat-input
   ├─ textarea [rows=2] [placeholder] [value=draft]
   └─ button [disabled=!draft.trim()] → "Envoyer"
```

### Interactions
- Boutons de mode → `onSetSpecMode("interview" | "brainstorm")` (App → POST spec-mode).
- Textarea : `onChange` → `setDraft` ; `onKeyDown` : **Entrée sans Shift** → `preventDefault()` + `send()` (Shift+Entrée = retour à la ligne).
- Bouton « Envoyer » → `send()` (App → `sendChat(projectId, message)`).
- Boutons de l'offre → `onResolveBrainstorm(true|false)` (App → `resolveBrainstorm`).

### i18n (namespace `chatPanel`) — libellés FR
`heading` « Chat — spécification & feedback » ; `specModeGroup` « Mode de spécification » ; `interview` « 💬 Interview » ; `interviewTitle` « Interview socratique : clarifier le besoin par une série de questions ciblées, dimension par dimension. » ; `brainstorming` « 🧠 Brainstorming » ; `brainstormingTitle` « Brainstorming : le PM/analyste re-questionne lui-même le besoin (divergence puis convergence). » ; `emptySpec` « Le PM va te poser des questions pour cadrer le besoin — réponds ci-dessous. » ; `emptyBuild` « Les échanges PM → PO → QA → Dev s'afficheront ici. Tu peux aussi envoyer un feedback à tout moment. » ; `placeholderSpec` « Réponds au PM… » ; `placeholderBuild` « Donne une consigne au dev en cours… (prise en compte aux prochaines tentatives) » ; `placeholderFeedback` « Donne ton feedback sur l'itération en cours… » ; `brainstormOfferGroup` « Proposition de brainstorming » ; `brainstormOfferLead` « 💡 Ton idée est encore ouverte. Une session de  » ; `brainstormOfferWord` « brainstorming » ; `brainstormOfferTrail` «  pour l'affiner ? » ; `brainstormTechniques` «  Techniques : {list}. » ; `brainstormAccept` « 🧠 Oui, on explore ensemble » ; `brainstormRefuse` « 🤖 Non, affine en autonomie » ; `send` « Envoyer » ; rôles : `roleUser` « Toi », `rolePm` « 📋 PM », `rolePo` « 🏃 PO », `roleDev` « 💻 Dev », `roleAnalyst` « 🔍 Analyste », `roleArchitect` « 🏛️ Architecte », `roleQa` « 🧪 QA », `roleCritic` « 🧐 Critique », `roleJudge` « ⚖️ Juge », `roleSystem` « ⚙️ Système ».

---

## DepGraphPanel

**Fichier** : `frontend/src/components/DepGraphPanel.tsx`

### Rôle et emplacement
Vue « Graphe de dépendances » du DAG des work items, rendue par `WorkspaceViews` (onglet « 🔗 Graphe », visible seulement si au moins une story a des tasks ou des `depends_on`). Un nœud par élément ordonnançable (task / US sans tasks / task de TS), disposé en **colonnes topologiques** (chaque colonne = vague parallélisable), avec le **chemin critique** surligné. Rendu **SVG pur** (pas de lib de graphe).

### Constantes de layout
```ts
const COL = 190;    // espacement horizontal entre colonnes (layers)
const ROW = 52;     // espacement vertical entre nœuds d'une colonne
const NODE_W = 150; // largeur d'un nœud
const NODE_H = 34;  // hauteur d'un nœud
const PAD = 16;     // marge intérieure du SVG
```

### Props (interface `Props`)
| Prop | Type | Oblig. |
|---|---|---|
| `stories` | `UserStory[]` | oui |
| `streams` | `Stream[]` | non |
| `onOpenItem` | `(storyId: string) => void` | non (clic nœud → ouvrir sa story/TS conteneuse sur le Board) |

### Sous-fonction interne : `nodeState(item, items): string`
Statut visuel d'un nœud (couleur) : les statuts terminaux gagnent — `done`→`done`, `in_progress`→`in_progress`, `failed`→`failed`, `red`→`red` ; sinon (`todo`) : `blockedBy(item.id, items).length > 0` → `"blocked"`, sinon `"ready"`.

### State, refs, effects
Pas de state ni d'effect ; deux `useMemo` :
1. `technicalIds` : `Set` des ids des stories `technical` (Technical Stories → préfixe 🔧).
2. Bloc `{items, layout, positions, width, height}` (deps `[stories, streams]`) :
   - `items = buildWorkGraph(stories ?? [], streams ?? [])` (`src/work.ts`) : une US sans tasks = 1 item ; une US décomposée = 1 item par task ; les deps US→US s'étendent aux **tasks feuilles** de l'US visée (récursif via `parent_id` pour les TS) ; une task hérite des deps de son US ; deps inconnues abandonnées (miroir du backend).
   - `layout = computeGraphLayout(items)` : `layer` (colonne = plus long chemin depuis une source, mémoïsé, défensif face aux cycles), `maxLayer`, `critical` (Set des ids d'un plus long chemin, remonté depuis le nœud le plus profond vers sa dépendance la plus profonde), `maxParallel` (colonne la plus large).
   - `positions` : dans chaque colonne, empilement **stable par ordre d'insertion** — `x = PAD + layer*COL`, `y = PAD + row*ROW`.
   - `width = PAD*2 + (maxLayer+1)*COL` ; `height = PAD*2 + max(1, maxParallel)*ROW`.
- **Early return** : `if (items.size === 0) return null;`
- Arêtes : pour chaque item, pour chaque `dep` de `dependsOn` présent dans `items` → `{from: dep, to: it.id, crit: critical.has(dep) && critical.has(it.id)}`.

### Structure DOM
```
div.dag-panel
├─ div.dag-summary [data-testid="dag-summary"]
│  → "{n} éléments · {waves} vagues · jusqu'à {parallel} en parallèle · chemin critique {critical}"
│    (n=items.size, waves=maxLayer+1, parallel=maxParallel, critical=critical.size)
└─ div.dag-scroll
   └─ svg.dag-svg [width] [height] [viewBox="0 0 {w} {h}"] [role="img"] [aria-label="Graphe de dépendances"]
      ├─ defs
      │  └─ marker#dag-arrow [viewBox="0 0 8 8"] [refX=7] [refY=4] [markerWidth=6] [markerHeight=6] [orient="auto-start-reverse"]
      │     └─ path [d="M0,0 L8,4 L0,8 z"] [fill="#5a6680"]
      ├─ (pour chaque arête, clé "e-{i}")
      │  path.dag-edge[.dag-edge-crit] [markerEnd="url(#dag-arrow)"] [fill="none"]
      │     d = "M{x1},{y1} C{midx},{y1} {midx},{y2} {x2},{y2}"   (courbe de Bézier ;
      │         x1=a.x+NODE_W, y1=a.y+NODE_H/2, x2=b.x, y2=b.y+NODE_H/2, midx=(x1+x2)/2)
      └─ (pour chaque nœud)
         g.dag-node.dag-node-{state}[.dag-node-crit] [transform="translate(x,y)"] [onClick] [data-testid="dag-node-{id}"]
         ├─ rect [width=150] [height=34] [rx=6]
         ├─ text.dag-node-id [x=8] [y=14] → "🔧 " si Technical Story, puis it.id
         └─ text.dag-node-title [x=8] [y=27] → (it.title || "").slice(0, 22)   (titre tronqué à 22 caractères)
```
États de nœud possibles (classe `dag-node-*`) : `done`, `in_progress`, `failed`, `red`, `blocked`, `ready`.

### Interactions
- Clic sur un `g.dag-node` → `open(it)` = `onOpenItem?.(it.storyId)` (WorkspaceViews → ouvre la story sur le Board).

### i18n (namespace `depGraph`)
| Clé | FR |
|---|---|
| `depGraph.title` | Graphe de dépendances |
| `depGraph.summary` | {n} éléments · {waves} vagues · jusqu'à {parallel} en parallèle · chemin critique {critical} |

### Diagramme
```
dag-summary: "7 éléments · 3 vagues · jusqu'à 3 en parallèle · chemin critique 3"
      colonne 0 (sources)   colonne 1            colonne 2
      ┌───────────┐          ┌───────────┐        ┌───────────┐
      │ US-1      │──────▶  │ T-3       │─────▶ │ 🔧 TS-1   │   ← chemin critique
      │ Titre…    │          │ Titre…    │        │ Titre…    │      (edges .dag-edge-crit)
      └───────────┘     ┌──▶└───────────┘        └───────────┘
      ┌───────────┐     │
      │ T-2       │─────┘   ┌───────────┐
      └───────────┘          │ T-4       │
      ┌───────────┐          └───────────┘
      │ US-5      │
      └───────────┘
      x = PAD + layer*190 ; y = PAD + row*52 ; nœud 150×34, rx=6
```

---

## CodeViewer

**Fichier** : `frontend/src/components/CodeViewer.tsx`

### Rôle et emplacement
Explorateur du **code généré** du workspace projet : un bouton « 📁 Code généré » (rendu par App **en bas de `div.col-right`**, après RunPanel) qui ouvre un overlay plein écran avec liste de fichiers à gauche et contenu brut à droite. **Pas de coloration syntaxique** : le contenu est affiché tel quel dans un `<pre>` (classe `code-viewer-pre`).

### Props
| Prop | Type | Oblig. |
|---|---|---|
| `projectId` | `string` | oui |

### State, refs, effects
- `open: boolean` — overlay ouvert.
- `files: string[]` — chemins POSIX relatifs, triés (fournis par l'API).
- `selected: string | null` — fichier sélectionné.
- `file: FileContent | null` — `{path, content, truncated}`.
- `listError`, `fileError: string` ; `loadingList`, `loadingFile: boolean`.
- **Effect 1** (deps `[open, projectId]`) : à l'ouverture, reset (`files=[]`, `selected=null`, `file=null`, `listError=""`), `loadingList=true`, puis `listFiles(projectId)` (GET `/api/projects/{id}/files`) → `setFiles(res.files)` et **auto-sélection du premier fichier** s'il existe ; erreur → `listError=String(e)` ; flag `cancelled`.
- **Effect 2** (deps `[open, selected, projectId]`) : si fermé ou rien de sélectionné → `setFile(null)` ; sinon `readFile(projectId, selected)` (GET `/api/projects/{id}/files/...`) → `setFile(res)` ; erreur → `file=null`, `fileError=String(e)` ; flag `cancelled`.

### Structure DOM
```
<> (fragment)
├─ button.ghost.code-viewer-btn → "📁 Code généré"
└─ [open] div.code-viewer-overlay [onClick → setOpen(false)]
   └─ div.code-viewer-panel [onClick → stopPropagation]
      ├─ div.code-viewer-header
      │  ├─ span.code-viewer-title → "📁 Code généré"
      │  └─ button.ghost.code-viewer-close [aria-label="Fermer"] → "✕"
      └─ div.code-viewer-body
         ├─ div.code-viewer-files
         │  ├─ [loadingList] div.code-viewer-muted → "Chargement…"
         │  ├─ [listError] div.code-viewer-error → listError
         │  ├─ [ni chargement ni erreur, 0 fichier] div.code-viewer-muted → "Aucun fichier."
         │  └─ (pour chaque f) button.code-viewer-file[.active si sélectionné] [title=f] → f
         └─ div.code-viewer-content
            ├─ [loadingFile] div.code-viewer-muted → "Chargement…"
            ├─ [fileError] div.code-viewer-error → fileError
            ├─ [fichier chargé]
            │  ├─ [file.truncated] div.code-viewer-truncated → "(fichier tronqué)"
            │  └─ pre.code-viewer-pre → file.content
            └─ [rien de sélectionné] div.code-viewer-muted → "Sélectionnez un fichier."
```

### Interactions
- Bouton d'ouverture → `setOpen(true)` ; clic sur l'overlay → fermeture ; clic dans le panneau → `stopPropagation` ; « ✕ » → fermeture.
- Clic sur un fichier → `setSelected(f)` (déclenche l'Effect 2).

### i18n
`codeViewer.generatedCode` « Code généré » ; `codeViewer.noFiles` « Aucun fichier. » ; `codeViewer.truncated` « (fichier tronqué) » ; `codeViewer.selectFile` « Sélectionnez un fichier. » ; `common.close` « Fermer » ; `common.loading` « Chargement… ».

---

## Stepper

**Fichier** : `frontend/src/components/Stepper.tsx`

### Rôle et emplacement
Stepper horizontal des étapes de BUILD pour **UN work item** (B-UX), rendu par `Activity.tsx` dans chaque ligne d'activité (`<Stepper view={view} now={now} tickTs={tickTs}/>`). Affiche chaque étape comme une cellule (done/active/failed/pending), le temps écoulé sur l'étape active, une sous-ligne d'auto-réparation (ex. « affinage 2/3 »), et se grise (« stale ») quand le heartbeat est trop vieux.

### Constante exportée
```ts
export const STALE_MS = 25_000; // un tick plus vieux que 25 s ⇒ stepper "stale" (grisé)
```

### Props
| Prop | Type | Oblig. |
|---|---|---|
| `view` | `ItemView` (`src/work.ts` : `{id, kind, status, stage, stageStartedAt, persona, recovery, guidance, fromTick}`) | oui |
| `now` | `number` (epoch ms, sert au temps écoulé + staleness) | oui |
| `tickTs` | `number` (epoch ms du heartbeat ; 0/undefined = données persistées) | non |

### Logique (helpers de `src/work.ts`)
- `STAGE_ORDER: BuildStage[] = ["queued","analyzing","contracts","implementing","verifying","merge_wait","merging","done"]` — « failed » partage le dernier slot avec « done ».
- `isStageDone(cell, current)` : done si le stage courant est strictement après la cellule (ou item `done`) ; jamais done si `failed`.
- `isStageActive(cell, current)` : la cellule est exactement le stage courant, item ni done ni failed.
- `elapsedLabel(startedAt, now)` : `""` si jamais démarré ou horloge décalée ; `<60s` → `"{s}s"` ; `<60m` → `"{m}m {s}s"` ; sinon `"{h}h {m}m"`.
- Calculs locaux : `stale = view.fromTick && !!tickTs && now - tickTs > STALE_MS` ; `failed = view.status === "failed" || view.stage === "failed"` ; `isTerminalFail = failed && cell === "done"` (la dernière cellule affiche « Échec » en état `failed`) ; état de cellule = `failed` / `active` / `done` / `pending`.
- `STAGE_LABEL` FR : `queued`→« File », `analyzing`→« Analyse », `contracts`→« Contrats », `implementing`→« Code », `verifying`→« Vérif », `merge_wait`→« Attente merge », `merging`→« Merge », `done`→« Fini », `failed`→« Échec ».
- `RECOVERY_LABEL` FR : `refining`→« affinage », `critic_restored`→« critique restaurée », `regression_rerun`→« rejeu régression », `mutation_rerun`→« rejeu mutation », `retry`→« nouvelle tentative ». `recLabel` = libellé du `view.recovery.kind` (fallback : kind brut) ; suffixe compteur `" {attempt}/{max_attempts}"` seulement si `max_attempts > 0`.

### Structure DOM
```
div.stepper[.stepper-stale] [role="group"] [aria-label="Étapes {view.id}"]
                            [data-testid="stepper-{view.id}"] [data-stale="true|false"]
├─ ol.stepper-track
│  └─ (pour chaque cell de STAGE_ORDER)
│     li.stepper-cell.stepper-{state} [data-testid="stage-{view.id}-{cell}"]
│        [data-state="done|active|failed|pending"] [aria-current="step" si active] [title=cellLabel]
│     ├─ span.stepper-dot [aria-hidden="true"]
│     ├─ span.stepper-cell-label → cellLabel   ("Échec" sur la cellule "done" si failed)
│     └─ [active && elapsed] span.stepper-elapsed → elapsed (ex. "1m 12s")
└─ [recLabel] div.stepper-recovery [data-testid="recovery-{view.id}"]
   → "🔧 {recLabel}" + (" {attempt}/{max_attempts}" si max_attempts > 0)   (ex. "🔧 affinage 2/3")
```

### Interactions
Aucune (composant purement informatif ; les actions par item sont dans la ligne Activity qui l'entoure).

### i18n (namespace `stepper`)
`stepsLabel` « Étapes {id} » ; stages : « File », « Analyse », « Contrats », « Code », « Vérif », « Attente merge », « Merge », « Fini », « Échec » ; recovery : « affinage », « critique restaurée », « rejeu régression », « rejeu mutation », « nouvelle tentative ».

---

## ComponentsPanel

**Fichier** : `frontend/src/components/ComponentsPanel.tsx`

### Rôle et emplacement
Panneau « 🧱 Composants du produit » dans `div.col-left` (après ChatPanel). Liste les composants techniques proposés par l'agent solutionneur (backend, frontend, BDD…) ; l'utilisateur approuve/écarte chacun, puis lance la création réelle (setup : dossiers, manifests). Rendu dans un `CollapsibleSection`.

### Constante
```ts
const KIND_ICON: Record<string, string> = {
  backend: "⚙️", frontend: "🖥️", database: "🗄️", cache: "⚡", other: "📦",
}; // fallback "📦"
```

### Props (interface `Props`)
| Prop | Type | Oblig. |
|---|---|---|
| `components` | `ProductComponent[]` (`{id, kind, name, technology, rationale, optional, status}`) | oui |
| `onUpdate` | `(components: ProductComponent[]) => void` | oui |
| `onSetup` | `() => void` | oui |

### State / logique
- Pas de state local. **Early return** : `null` si `components.length === 0`.
- `STATUS_LABEL` : `proposed`→« proposé », `approved`→« approuvé », `created`→« créé », `rejected`→« écarté ».
- `toggle(target)` : no-op si `status === "created"` (déjà matérialisé) ; sinon reconstruit le tableau en basculant le composant ciblé `approved ⇄ rejected` et appelle `onUpdate(next)` (App → `updateComponents`).
- `approvedCount` = nombre de composants `approved` ou `created` ; le bouton setup est `disabled` si 0.

### Structure DOM
```
CollapsibleSection [title="🧱 Composants du produit"] [className="components"]
└─ (panel-body)
   ├─ div.component-list
   │  └─ (pour chaque c) div.component.status-{c.status}
   │     ├─ span.component-icon → KIND_ICON[c.kind] ?? "📦"
   │     ├─ span.component-name → c.name
   │     │  ├─ span.component-tech → " — {c.technology}"
   │     │  └─ [c.optional] span.component-optional → " (optionnel)"
   │     ├─ span.state-tag.component-status-{c.status} → STATUS_LABEL[c.status]
   │     └─ [status !== "created"] button.small-btn
   │        [title = approved ? "Écarter ce composant" : "Approuver ce composant"]
   │        → approved ? "✕" : "✓"
   └─ button.primary.setup-btn [disabled=approvedCount===0]
      [title="Créer réellement les composants approuvés (dossiers, manifests)"]
      → "🧱 Créer les composants approuvés"
```

### Interactions
- Bouton ✓/✕ → `toggle(c)` → `onUpdate` (PATCH composants côté App).
- Bouton setup → `onSetup()` (App → `setupComponents(projectId)`).

### i18n (namespace `componentsPanel`)
`title` « 🧱 Composants du produit » ; `optional` « (optionnel) » ; `approve` « Approuver ce composant » ; `reject` « Écarter ce composant » ; `setup` « 🧱 Créer les composants approuvés » ; `setupTitle` « Créer réellement les composants approuvés (dossiers, manifests) » ; statuts « proposé / approuvé / créé / écarté ».

---

## SettingsModal

**Fichier** : `frontend/src/components/SettingsModal.tsx`

### Rôle et emplacement
Fenêtre « Paramètres » : bascule du **thème** (sombre/clair) et de la **langue** (en/fr). Rendue par App quand `showSettings` est vrai : `{showSettings && <SettingsModal onClose={...}/>}`. Les deux préférences sont persistées en `localStorage` (`autospec.theme`, `autospec.lang`) par les stores `i18n/theme.ts` et `i18n/i18n.ts`, et appliquées immédiatement à toute l'app (`<html data-theme>` / `<html lang>`).

### Props
| Prop | Type | Oblig. |
|---|---|---|
| `onClose` | `() => void` | oui |

### Hooks
- `useI18n()` → `{t, lang, setLang}` ; `useTheme()` → `{theme, setTheme}`. Pas de state local.
- `LANGS` (exporté par `i18n.ts`) : `[{value:"en", label:"English", flag:"🇬🇧"}, {value:"fr", label:"Français", flag:"🇫🇷"}]`.

### Structure DOM
```
div.modal-backdrop [onClick=onClose]
└─ div.modal.settings-modal [role="dialog"] [aria-modal="true"] [aria-label="Paramètres"] [onClick → stopPropagation]
   ├─ button.modal-close [title="Fermer"] [aria-label="Fermer"] → "✕"
   ├─ h2 → "⚙️ Paramètres"
   ├─ section.settings-section (Apparence)
   │  ├─ div.settings-section-title → "Apparence"
   │  ├─ p.settings-hint → "Bascule entre le thème sombre et clair."
   │  └─ div.settings-row
   │     ├─ span.settings-row-label → "Thème"
   │     └─ div.settings-segmented [role="group"] [aria-label="Thème"]
   │        ├─ button [aria-pressed=theme==="dark"]  → "🌙 Sombre"
   │        └─ button [aria-pressed=theme==="light"] → "☀️ Clair"
   └─ section.settings-section (Langue)
      ├─ div.settings-section-title → "Langue"
      ├─ p.settings-hint → "Change la langue de l'interface."
      └─ div.settings-row
         ├─ span.settings-row-label → "Langue"
         └─ div.settings-segmented [role="group"] [aria-label="Langue"]
            └─ (pour chaque l de LANGS) button [aria-pressed=lang===l.value] → "{l.flag} {l.label}"
               ("🇬🇧 English" / "🇫🇷 Français")
```

### Interactions
- Backdrop / « ✕ » → `onClose()`.
- « 🌙 Sombre » / « ☀️ Clair » → `setTheme("dark"|"light")` (pose `data-theme` sur `<html>` ; variables CSS sous `:root[data-theme="dark|light"]`).
- Bouton langue → `setLang(l.value)` (pose `lang` sur `<html>`, notifie tous les composants abonnés).

### i18n (namespace `settings`)
`title` « Paramètres » ; `appearance` « Apparence » ; `theme` « Thème » ; `themeDark` « Sombre » ; `themeLight` « Clair » ; `themeHint` « Bascule entre le thème sombre et clair. » ; `language` « Langue » ; `languageHint` « Change la langue de l'interface. » ; `common.close` « Fermer ».

---

## ProjectSetup

**Fichier** : `frontend/src/components/ProjectSetup.tsx`

### Rôle et emplacement
Formulaire « Nouveau projet / feature ». Rendu par App **dans une modale** (`div.modal-backdrop > div.modal`, avec bouton `.modal-close` « ✕ » si `canCloseSetup`) quand `showSetup` est vrai.

### Props (interface `Props`)
| Prop | Type | Oblig. |
|---|---|---|
| `onCreate` | `(goal: string, name: string, autoSpec: boolean, budgetUsd: number, brief?: string, brownfieldPath?: string) => void` | oui |
| `busy` | `boolean` | oui |

### State
- `goal: string` ("") — description de la feature/projet (champ obligatoire de fait : bouton disabled si vide).
- `name: string` ("") — nom du projet (optionnel).
- `autoSpec: boolean` (false) — mode boucle auto-spec.
- `budget: string` ("") — budget max en $, champ texte numérique.
- `brief: string` ("") — spec à importer (court-circuite l'interview).
- `brownfield: string` ("") — chemin d'un repo existant à étendre.
Pas de refs ni d'effects.

### Structure DOM
```
div.panel.setup
├─ h2 → "Nouveau projet / feature"
├─ input [placeholder="Nom du projet (optionnel)"] [value=name]
├─ textarea [rows=6] [placeholder="Décris la feature ou le projet que tu veux créer…"] [value=goal]
├─ label.autospec-toggle
│  ├─ input[type=checkbox] [checked=autoSpec]
│  └─ span → <strong>"Auto-spec"</strong> " " "— le PM décide de tout seul et enchaîne les itérations en boucle jusqu'à l'arrêt manuel"
├─ textarea [rows=4] [placeholder="Spec à importer (optionnel) — colle un cahier des charges pour court-circuiter l'interview"] [value=brief]
├─ input [aria-label="Chemin d'un repo existant à étendre (mode brownfield, optionnel)"]
│        [placeholder="Repo existant à étendre (chemin, optionnel — mode brownfield)"] [value=brownfield]
├─ input[type=number] [min=0] [step=0.1]
│        [aria-label="Budget maximum en dollars (vide = pas de limite)"]
│        [placeholder="Budget max ($) — vide = pas de limite"] [value=budget]
└─ button.primary [disabled=busy || !goal.trim()]
   → autoSpec ? "🔁 Lancer la boucle auto-spec" : "🚀 Démarrer la spécification"
```

### Interactions
- Chaque champ → setter correspondant.
- Bouton → `onCreate(goal.trim(), name.trim(), autoSpec, Number(budget) || 0, brief.trim() || undefined, brownfield.trim() || undefined)` (App → `handleCreate` → POST création de projet).

### i18n (namespace `projectSetup`)
`title` « Nouveau projet / feature » ; `namePlaceholder` « Nom du projet (optionnel) » ; `goalPlaceholder` « Décris la feature ou le projet que tu veux créer… » ; `autoSpecLabel` « Auto-spec » ; `autoSpecDescription` « — le PM décide de tout seul et enchaîne les itérations en boucle jusqu'à l'arrêt manuel » ; `briefPlaceholder` « Spec à importer (optionnel) — colle un cahier des charges pour court-circuiter l'interview » ; `brownfieldAriaLabel` « Chemin d'un repo existant à étendre (mode brownfield, optionnel) » ; `brownfieldPlaceholder` « Repo existant à étendre (chemin, optionnel — mode brownfield) » ; `budgetAriaLabel` « Budget maximum en dollars (vide = pas de limite) » ; `budgetPlaceholder` « Budget max ($) — vide = pas de limite » ; `submitAutoSpec` « 🔁 Lancer la boucle auto-spec » ; `submitSpec` « 🚀 Démarrer la spécification ».

---

## Dashboard

**Fichier** : `frontend/src/components/Dashboard.tsx`

### Rôle et emplacement
Modale « 📊 Dashboard de l'usine » : métriques agrégées de la fabrique (tous projets). Rendue par App quand `showDashboard` est vrai (bouton d'ouverture dans la barre du haut).

### Sous-composant interne : `Stat`
```
Props: { label: string; value: string | number }
div.metric-card
├─ div.metric-value → value
└─ div.metric-label → label
```

### Props
| Prop | Type | Oblig. |
|---|---|---|
| `onClose` | `() => void` | oui |

### State, effects
- `metrics: Metrics | null` (null) ; `error: string` ("").
- **Effect** (au montage, `[]`) : `getMetrics()` (GET `/api/metrics`) → `setMetrics` ; erreur → `setError(errorMessage(e))`.
- Helper `pct(v: number | null)` : `v != null ? "{v}/100" : "—"`.

### Structure DOM
```
div.modal-backdrop [onClick=onClose]
└─ div.modal.dashboard [onClick → stopPropagation]
   ├─ div.dashboard-head
   │  ├─ h2 → "📊 Dashboard de l'usine"
   │  └─ button.ghost.small-btn [aria-label="Fermer"] → "✕"
   ├─ [error] div.edit-error → error
   └─ [!metrics] p.placeholder → "Chargement…"
      [sinon] div.metrics-grid  (14 <Stat/> dans cet ordre)
      ├─ Stat "Projets"          = metrics.projects
      ├─ Stat "Coût total"       = "$" + total_cost_usd.toFixed(4)
      ├─ Stat "Appels agent"     = total_agent_calls
      ├─ Stat "Stories"          = total_stories
      ├─ Stat "Terminées"        = stories_done
      ├─ Stat "Échouées"         = stories_failed
      ├─ Stat "Taux de succès"   = "{success_rate}%"
      ├─ Stat "Tentatives moy."  = avg_attempts
      ├─ Stat "Coût / story"     = "$" + cost_per_story.toFixed(4)
      ├─ Stat "Qualité moy."     = pct(avg_quality)      ("x/100" ou "—")
      ├─ Stat "Mutation moy."    = pct(avg_mutation)
      ├─ Stat "Couverture moy."  = avg_coverage != null ? "{avg_coverage}%" : "—"
      ├─ Stat "Findings"         = findings
      └─ Stat "Régressions"      = regressions
```

### Interactions
- Backdrop / « ✕ » → `onClose()`.

### i18n (namespace `dashboard`)
`title` « 📊 Dashboard de l'usine » ; `projects` « Projets » ; `totalCost` « Coût total » ; `agentCalls` « Appels agent » ; `stories` « Stories » ; `done` « Terminées » ; `failed` « Échouées » ; `successRate` « Taux de succès » ; `avgAttempts` « Tentatives moy. » ; `costPerStory` « Coût / story » ; `avgQuality` « Qualité moy. » ; `avgMutation` « Mutation moy. » ; `avgCoverage` « Couverture moy. » ; `findings` « Findings » ; `regressions` « Régressions » ; `common.loading` « Chargement… » ; `common.close` « Fermer ».

---

## PlanReviewPanel

**Fichier** : `frontend/src/components/PlanReviewPanel.tsx`

### Rôle et emplacement
Panneau « Revue du plan » (étape REVIEW_PLAN) : score qualité du plan PO + problèmes signalés et améliorations proposées par l'agent **critic**. Dernier panneau de `div.col-left`. Masqué tant que la revue n'a pas tourné.

### Props (interface `Props`)
| Prop | Type | Oblig. |
|---|---|---|
| `planQuality` | `number` (−1 = pas encore de revue) | oui |
| `issues` | `string[]` | oui |
| `suggestions` | `string[]` | oui |

### Logique
- `ran = planQuality >= 0`. **Early return** `null` si `!ran && issues.length === 0 && suggestions.length === 0`.
- `scoreClass` : `>= 80` → `"good"` ; `>= 50` → `"mid"` ; sinon `"low"`.

### Structure DOM
```
CollapsibleSection [title="Revue du plan"] [className="plan-review"]
└─ (panel-body)
   ├─ [ran] div.plan-review-score.plan-review-score-{good|mid|low} [data-testid="plan-review-score"]
   │        → "Qualité du plan : " <strong>"{planQuality}/100"</strong>
   ├─ [issues.length>0] div.plan-review-block
   │  ├─ div.plan-review-heading → "Problèmes signalés"
   │  └─ ul.plan-review-list.plan-review-issues
   │     └─ (chaque issue, clé "i-{i}") li → "⚠ {texte}"
   ├─ [suggestions.length>0] div.plan-review-block
   │  ├─ div.plan-review-heading → "Améliorations proposées"
   │  └─ ul.plan-review-list.plan-review-suggestions
   │     └─ (chaque suggestion, clé "s-{i}") li → "→ {texte}"
   └─ [ran && 0 issue && 0 suggestion] div.plan-review-clean
      → "Aucun problème signalé — le découpage paraît bien dimensionné."
```

### Interactions
Aucune propre (seul le repli du `CollapsibleSection`).

### i18n (namespace `planReviewPanel`)
`title` « Revue du plan » ; `score` « Qualité du plan : » ; `issues` « Problèmes signalés » ; `suggestions` « Améliorations proposées » ; `clean` « Aucun problème signalé — le découpage paraît bien dimensionné. ».

---

## LanguagePanel

**Fichier** : `frontend/src/components/LanguagePanel.tsx`

### Rôle et emplacement
Panneau « 🧭 Langage backend » (L2) : langage recommandé par l'analyse complexité/criticité + override utilisateur. Dans `div.col-left` (après ComponentsPanel). Ne s'affiche qu'une fois l'analyse faite.

### Props (interface `Props`)
| Prop | Type | Oblig. |
|---|---|---|
| `language` | `"python" \| "go" \| "rust"` | non |
| `complexity` | `number` | non |
| `criticality` | `number` | non |
| `rationale` | `string` | non |
| `onSet` | `(language: "python" \| "go" \| "rust") => void` | oui |

### Logique
- `LANGS` local (valeurs/émojis non traduits) : `python`→« 🐍 Python », `go`→« 🐹 Go », `rust`→« 🦀 Rust ».
- `analyzed = (complexity ?? -1) >= 0 || (criticality ?? -1) >= 0`. **Early return** `null` si `!analyzed || !language`.

### Structure DOM
```
CollapsibleSection [title="🧭 Langage backend"] [className="language"]
└─ (panel-body)
   ├─ div.language-scores
   │  ├─ span.language-score [title="Complexité technique estimée (1-5)"]
   │  │  → "Complexité " <strong>"{complexity}/5"</strong>
   │  └─ span.language-score [title="Criticité / sensibilité aux erreurs (1-5)"]
   │     → "Criticité " <strong>"{criticality}/5"</strong>
   ├─ [rationale] p.language-rationale → rationale
   └─ label.language-override
      ├─ span → "Langage"
      └─ select [aria-label="Langage backend"] [value=language]
         └─ option × 3 → "🐍 Python" / "🐹 Go" / "🦀 Rust"
```

### Interactions
- `select.onChange` → `onSet(e.target.value as "python"|"go"|"rust")` (App → `setLanguage(projectId, lang)`).

### i18n (namespace `languagePanel`)
`title` « 🧭 Langage backend » ; `complexity` « Complexité » ; `complexityTitle` « Complexité technique estimée (1-5) » ; `criticality` « Criticité » ; `criticalityTitle` « Criticité / sensibilité aux erreurs (1-5) » ; `languageLabel` « Langage » ; `selectAriaLabel` « Langage backend ».

---

## BacklogPanel

**Fichier** : `frontend/src/components/BacklogPanel.tsx`

### Rôle et emplacement
Panneau « Backlog de l'analyste (kanban) » : hypothèses de features (`FeatureHypothesis`) proposées/priorisées par l'analyste. Dans `div.col-left` (après LanguagePanel).

### Props (interface `Props`)
| Prop | Type | Oblig. |
|---|---|---|
| `backlog` | `FeatureHypothesis[]` (`{id, title, rationale, value, complexity, status, rank}`) | oui |

### Logique
- **Early return** `null` si `backlog.length === 0`.
- `active` = hypothèses `status !== "done"` triées par `rank` croissant ; `shipped` = hypothèses `status === "done"`.
- `STATUS_LABEL` : `proposed`→« proposée », `selected`→« en cours », `done`→« livrée », `rejected`→« rejetée ».

### Structure DOM
```
CollapsibleSection [title="Backlog de l'analyste (kanban)"] [className="backlog"]
└─ (panel-body)
   └─ div.hypotheses
      ├─ (pour chaque h de active) div.hypothesis.hyp-{h.status} [title=h.rationale]
      │  ├─ span.hyp-rank → "#{h.rank}"
      │  ├─ span.hyp-title → h.title
      │  ├─ span.hyp-scores → "V{h.value} / C{h.complexity}"
      │  └─ span.badge.badge-hyp-{h.status} → STATUS_LABEL[h.status] ?? h.status
      └─ [shipped.length>0] div.hyp-shipped
         → "✅ Livrées : " + shipped.map(h => h.title).join(", ")
```

### Interactions
Aucune (lecture seule ; repli via `CollapsibleSection`).

### i18n (namespace `backlogPanel`)
`title` « Backlog de l'analyste (kanban) » ; `shipped` « Livrées : » ; statuts « proposée / en cours / livrée / rejetée ».

---

## ArchitecturePanel

**Fichier** : `frontend/src/components/ArchitecturePanel.tsx`

### Rôle et emplacement
Panneau « Architecture & qualité » : le design d'architecture texte produit par l'architecte + le score qualité du plan. Dans `div.col-left` (entre BacklogPanel et PlanReviewPanel).

### Props (interface `Props`)
| Prop | Type | Oblig. |
|---|---|---|
| `architecture` | `string` | oui |
| `planQuality` | `number` (−1 = pas de score) | oui |

### Logique
- `hasArchitecture = architecture.trim() !== ""` ; `hasPlanQuality = planQuality >= 0`. **Early return** `null` si ni l'un ni l'autre.

### Structure DOM
```
CollapsibleSection [title="Architecture & qualité"] [className="architecture"]
└─ (panel-body)
   ├─ [hasPlanQuality] div.plan-quality → "Qualité du plan : " <strong>"{planQuality}/100"</strong>
   └─ [hasArchitecture] pre.architecture-design → architecture   (texte brut préformaté)
```

### Interactions
Aucune (repli via `CollapsibleSection`).

### i18n (namespace `architecturePanel`)
`title` « Architecture & qualité » ; `planQuality` « Qualité du plan : ».

---

## CollapsibleSection

**Fichier** : `frontend/src/components/CollapsibleSection.tsx`

### Rôle et emplacement
Brique générique « panneau repliable » (UI5) : en-tête cliquable (caret + titre) qui plie/déplie le contenu. Utilisée par **ComponentsPanel, BacklogPanel, ArchitecturePanel, PlanReviewPanel, LanguagePanel** (et d'autres). Ces panneaux ne s'affichent déjà que lorsqu'ils ont du contenu ; ceci permet en plus de les replier quand la colonne de gauche se charge.

### Props
| Prop | Type | Oblig. |
|---|---|---|
| `title` | `string` | oui |
| `className` | `string` | oui (suffixe de classe du panel) |
| `defaultOpen` | `boolean` | non (défaut `true`) |
| `headerExtra` | `ReactNode` | non (contenu additionnel dans l'en-tête, après le h2) |
| `children` | `ReactNode` | oui |

### State
- `open: boolean` (init `defaultOpen`).

### Structure DOM
```
div.panel.{className}[.panel-collapsed si fermé]
├─ button.panel-header-btn [aria-expanded=open] [onClick → setOpen(o => !o)]
│  ├─ span.panel-caret [aria-hidden="true"] → open ? "▾" : "▸"
│  ├─ h2 → title
│  └─ [headerExtra]
└─ [open] div.panel-body → children
```

### Interactions
- Clic sur l'en-tête → bascule `open` (le corps est **démonté** quand fermé, pas seulement masqué).

### i18n
Aucune clé propre (le titre est fourni traduit par l'appelant).

---

## Annexe — dépendances transverses utilisées par ces composants

- **`src/work.ts`** : `buildWorkGraph`, `computeGraphLayout` (`GraphLayout {layer, maxLayer, critical, maxParallel}`), `blockedBy(itemId, items)`, `WorkItem {id, kind, storyId, stream, title, status, dependsOn}` (DepGraphPanel) ; `STAGE_ORDER`, `isStageActive`, `isStageDone`, `elapsedLabel`, `ItemView` (Stepper).
- **`src/components/Board.tsx`** : `epicProgress(stories)` → `{total, done, inProgress, failed, pct, state}` avec `state ∈ working|failed|done|pending` (calculé sur les statuts **effectifs**), et `EpicProgressBar` (`div.epic-progress[role=progressbar]` + `div.epic-progress-fill.state-{state}` avec `width: {pct}%`, puis `div.epic-card-meta` avec compteurs) — réutilisés par IterationsView.
- **`src/api.ts`** : `getIterations(projectId)` → `number[]` ; `listFiles(projectId)` → `FileListing {files}` ; `readFile(projectId, path)` → `FileContent {path, content, truncated}` ; `getMetrics()` → `Metrics` ; `errorMessage(e)`.
- **`src/i18n/i18n.ts`** : store de langue module-level (clé localStorage `autospec.lang`, défaut `en`), `useI18n()`, `LANGS`. **`src/i18n/theme.ts`** : store de thème (clé `autospec.theme`, défaut `dark`), `useTheme()`, applique `data-theme` sur `<html>`.
