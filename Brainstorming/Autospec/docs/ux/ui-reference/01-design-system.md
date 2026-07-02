# Design system Autospec — référence UI (01)

Référence exhaustive du design system du frontend Autospec (React + Vite), permettant de recréer l'UI à l'identique. Sources : `frontend/src/index.css` (3533 lignes), `frontend/src/i18n/theme.ts`, `frontend/src/components/Logo.tsx`, `frontend/index.html`.

---

## 1. Fondations

### 1.1 Custom properties CSS (tokens)

Les variables vivent sous `:root[data-theme="dark|light"]`. Le sélecteur `:root, :root[data-theme="dark"]` fait du dark le défaut (avec `color-scheme: dark` — les scrollbars et contrôles natifs suivent le thème ; il n'y a **aucun style de scrollbar custom** dans le CSS).

#### Palette de base

| Variable | Dark | Light | Rôle |
|---|---|---|---|
| `--bg` | `#0f1117` | `#f4f6fb` | Fond de page (body) |
| `--panel` | `#181c25` | `#ffffff` | Fond des panneaux / header |
| `--panel-2` | `#1f2430` | `#eef1f7` | Fond secondaire (cartes, inputs, chips) |
| `--border` | `#2c3342` | `#d3d9e3` | Bordures |
| `--text` | `#e6e9f0` | `#1b2030` | Texte principal |
| `--muted` | `#8a93a6` | `#5b6677` | Texte secondaire |
| `--title` | `#aeb8cb` | `#41506a` | Titres de panneaux (h2), logo |
| `--accent` | `#4f8cff` | `#2f6fe0` | Accent (bleu) : actions, actif, running |
| `--green` | `#3ecf8e` | `#1f9d63` | Succès |
| `--red` | `#ff5c6c` | `#d83a4b` | Erreur / danger |
| `--amber` | `#ffb454` | `#b9781a` | Avertissement |

#### Tokens de grille adaptative (P1/P3)

| Variable | Valeur défaut | Rôle |
|---|---|---|
| `--rail-w` | `380px` | Largeur de la colonne gauche (rail) de `.workspace` |
| `--scene-w` | `1fr` | Largeur de la scène (colonne droite) |
| `--dock-w` | `0px` | Largeur du dock (drawer d'item, reste 0 — dock inline) |

#### Tokens de densité (P3)

| Variable | Défaut | <1200px | Rôle |
|---|---|---|---|
| `--font-sm` | `13px` | `12px` | Petite taille de texte (lignes d'activité) |
| `--row-pad` | `8px` | `4px` | Padding vertical des lignes d'activité |

Couplage : sous 1200px, `[data-density="compact"] .activity-row-title { font-size: var(--font-sm); }`.

#### Canal étapes/statuts colorblind-safe (P15)

Distinguables en teinte **et** en luminance.

| Variable | Dark | Light |
|---|---|---|
| `--stage-queued` | `#6b7689` | `#6b7689` |
| `--stage-active` | `#4f8cff` | `#2f6fe0` |
| `--stage-done` | `#3ecf8e` | `#1f9d63` |
| `--stage-failed` | `#ff5c6c` | `#d83a4b` |
| `--status-todo` | `#8a93a6` | `#5b6677` |
| `--status-running` | `#4f8cff` | `#2f6fe0` |
| `--status-blocked` | `#c08457` | `#a4631f` |
| `--status-done` | `#3ecf8e` | `#1f9d63` |
| `--status-failed` | `#ff5c6c` | `#d83a4b` |

#### Token d'attention réservé (P13/P15)

UN seul token d'attention + UNE seule pulsation, réservés à failed / blocked / needs-attention (rien d'autre ne doit pulser) :

| Variable | Dark | Light |
|---|---|---|
| `--attention` | `#ff5c6c` | `#d83a4b` |
| `--attention-bg` | `rgba(255, 92, 108, 0.12)` | `rgba(216, 58, 75, 0.1)` |

> Note : `.task-id` référence `var(--mono, monospace)` mais `--mono` n'est **jamais défini** — le fallback `monospace` s'applique.

### 1.2 Gestion du thème (`i18n/theme.ts`)

- Deux thèmes : `"dark"` (défaut) et `"light"`.
- Mécanisme : attribut `data-theme` posé sur `<html>` (`document.documentElement.setAttribute("data-theme", theme)`), qui active le bloc de variables correspondant.
- Persistance : `localStorage` sous la clé **`autospec.theme`** (lecture au boot via `loadInitialTheme()`, try/catch si localStorage indisponible → fallback dark).
- API : `getTheme()`, `setTheme(theme)` (no-op si identique, persiste puis notifie), `toggleTheme()`, `subscribeTheme(fn)` (Set de listeners, retourne un unsubscribe), `initTheme()` (applique le thème persisté au boot), et hook React `useTheme()` (`useReducer` compteur + `useEffect(subscribeTheme)` pour forcer le re-render).
- Le toggle est exposé dans la fenêtre Settings (segmented control `.settings-segmented`).

### 1.3 Typographie

- Police UI : `font-family: "Segoe UI", system-ui, sans-serif` (sur `body`).
- Police monospace : `Consolas, monospace` (code, logs, ids, scores, gherkin, diff, DAG).
- Tailles usuelles : 18px (h1 header, titre settings), 16px (titre détail story), 14px (labels settings, iter-num), 13px (base courante : h2 panneaux, boutons de menu, stories), 12px (texte secondaire, logs, badges de phase), 11px (méta, ids, hints), 10px (badges, prio, stepper labels), 9px (temps écoulé du stepper).
- Titres de panneaux (`.panel h2`) : `13px`, `font-weight: 700`, `text-transform: uppercase`, `letter-spacing: 0.07em`, couleur `var(--title)`.

### 1.4 Resets & base

```css
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: "Segoe UI", system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
}
```

Bouton par défaut (base de tous les boutons) :

```css
button {
  font: inherit;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  padding: 9px 14px;
  cursor: pointer;
}
button:disabled { opacity: 0.45; cursor: not-allowed; }
```

### 1.5 Constantes récurrentes

- Radius : 4px (crumb), 6px (petits blocs code, chips epic), 7px (task-row, guidance), 8px (inputs, boutons, cartes story, toasts), 9px (activity-row), 10px (panneaux, menus, epics, badges pills 10px), 12px (grands overlays), `99px`/`999px` (pills).
- Fond « code » (blocs pre) : `#11141b`, texte `#c6d4f0`, bordure `var(--border)`, radius 6–8px.
- Fond « sélection active » bleu foncé : `#1a2740` (chips actifs, fichier actif, drag-over).
- Élévations : header `box-shadow: 0 1px 4px rgba(0,0,0,0.3)` ; panneaux `0 1px 3px rgba(0,0,0,0.28)` ; menus popover `0 10px 28px rgba(0,0,0,0.45)` ; toasts `0 4px 14px rgba(0,0,0,0.35)`.

---

## 2. Tokens sémantiques (couleurs par rôle)

### 2.1 Agents / rôles de message (bordure gauche 3px des `.msg-*`)

| Rôle | Classe | Couleur |
|---|---|---|
| Utilisateur | `.msg-user` | `var(--accent)` `#4f8cff` |
| PM | `.msg-pm` | `var(--amber)` `#ffb454` |
| PO | `.msg-po` | `#b07cff` (violet) |
| Dev | `.msg-dev` | `var(--green)` `#3ecf8e` |
| Architect | `.msg-architect` | `#39c5bb` (teal) |
| Critic | `.msg-critic` | `#ff8a5c` (orange) |
| Judge | `.msg-judge` | `#ffd24a` (jaune) |
| System | `.msg-system` | `var(--muted)` + `opacity: 0.85` |

### 2.2 Statuts (badges, cartes, phases)

| Statut | Couleur | Où |
|---|---|---|
| todo | `var(--muted)` | `.badge-todo`, `.status-todo` |
| in_progress / running / build | `var(--accent)` | `.badge-in_progress`, `.story.status-in_progress`, `.phase-build`, `.count-running` |
| red (tests rouges) | `var(--red)` | `.badge-red`, `.story.status-red` |
| done / green | `var(--green)` | `.badge-done`, `.badge-green`, `.story.status-done`, `.phase-done`, `.count-done` |
| failed | blanc sur fond `var(--red)` (badge) ; carte : bordure rouge + fond `#2a1418` | `.badge-failed`, `.story.status-failed`, `.phase-error`, `.count-failed` |
| blocked | `--status-blocked` `#c08457` | stepper/status channel |

### 2.3 Couleurs ponctuelles hors tokens

| Valeur | Usage |
|---|---|
| `#3fb950` | vert GitHub : `.toast-success`, `.coverage-badge`, `.approve-btn` |
| `#d29922` | ambre : `.toast-warning`, `.approval-banner` (fond `#2b2410`) |
| `#e06c75` | rouge doux : `.toast-error`, `.run-error`, `.regression-banner` (fond `#2b1416`) |
| `#e0b341` | jaune DAG : arêtes/nœuds critiques, `.plan-review-score-mid` |
| `#c9b8f0` / `#2a2140` / `#4a3d72` | violet Technical Story (`.badge-technical`, `.story-ts-contract-heading`) |
| `#ffb4b4` | rouge pâle : `.blocked-badge`, `.merge-conflict`, `.activity-blockers` |
| `#e6b8b8` | rose : `.plan-review-issues li` |
| `#84aaff` | bleu clair du halo `dev-glow` à 50% |

### 2.4 Streams (multi-stream ST-12/13/14)

| Stream | Bordure | Texte |
|---|---|---|
| backend | `#4f8cff` | `#aac6ff` |
| frontend | `#c084fc` | `#e2c7ff` |
| cache | `#f0b429` | `#ffe2a0` |
| database | `#34d399` | `#b6f0d8` |
| other | `var(--border)` | `var(--muted)` |

---

## 3. Animations & keyframes

| Keyframes | Étapes | Durée / usage |
|---|---|---|
| `chip-pulse` | 0%/100% : `opacity:1; box-shadow: 0 0 0 0 rgba(79,140,255,0.55)` — 50% : `opacity:0.55; box-shadow: 0 0 0 4px rgba(79,140,255,0)` | `1.2s ease-in-out infinite` sur `.dot.pulse` (chip projet en cours) |
| `dev-glow` | 0%/100% : `box-shadow: 0 0 0 0 rgba(79,140,255,0); border-color: var(--accent)` — 50% : `box-shadow: 0 0 11px 1px rgba(79,140,255,0.5); border-color: #84aaff` | `1.6s ease-in-out infinite` sur `.epic-card.epic-working`, `.story.status-in_progress`, `.task-row.status-in_progress` |
| `spin` | `to { transform: rotate(360deg); }` | `0.7s linear infinite` sur `.spinner` |
| `toast-in` | `from { opacity:0; transform: translateY(8px); }` → `to { opacity:1; translateY(0); }` | `0.18s ease` à l'apparition d'un `.toast` |
| `attention-pulse` | 0%/100% : `box-shadow: 0 0 0 0 var(--attention-bg)` — 50% : `box-shadow: 0 0 0 4px rgba(255,92,108,0)` | `1.3s ease-in-out infinite` sur `.stepper-failed .stepper-dot` et `.attention-chip` (SEULE pulsation autorisée hors chips) |
| `llm-pulse` | `50% { opacity: 0.4; }` | `1.6s ease-in-out infinite` sur `.llm-live` |

Transitions ponctuelles : `.spec-mode-btn`/`.view-toggle button` (`background 0.15s, color 0.15s`), `.brainstorm-btn` (`background 0.15s, border-color 0.15s`), `.epic-card` (`border-color 0.12s ease, transform 0.12s ease`), `.epic-progress-fill` (`width 0.3s ease`).

**`prefers-reduced-motion: reduce`** (3 blocs) : coupe `dev-glow` sur epics/stories/tasks, ralentit `.spinner` à `1.4s`, coupe l'animation de `.stepper-failed .stepper-dot` et de `.attention-chip`.

---

## 4. Catalogue des classes CSS

### 4.1 Shell applicatif

| Classe | Rendu |
|---|---|
| `.app` | `flex column`, `height: 100vh` |
| `header` (élément) | flex, `align-items:center; justify-content:space-between`, padding `10px 18px`, `border-bottom: 1px solid var(--border)`, fond `var(--panel)`, `box-shadow: 0 1px 4px rgba(0,0,0,0.3)`, `z-index: 2` |
| `header h1` | 18px, margin 0, flex + `gap: 8px` (logo + titre) |
| `.app-logo` | `width/height: 1.35em`, `flex: none`, `color: var(--title)` (brackets du logo suivent la couleur de titre) |
| `.subtitle` | 12px, `var(--muted)`, `font-weight: normal`, `margin-left: 10px` |
| `main` | `flex: 1; min-height: 0; padding: 14px` |
| `.home` | flex centré (écran d'accueil) |
| `.workspace` | `display: grid; grid-template-columns: var(--rail-w) var(--scene-w); gap: 16px; height: 100%` |
| `.col-left`, `.col-right` | `flex column; gap: 14px; min-height: 0` |
| `.col-right .board` | `flex: 1.4` |
| `.col-right .run` | `flex: 1` |
| `.col-right .run.run-collapsed` | `flex: 0 0 auto` (UI4 : le panneau Exécution replié rend l'espace au Board) |
| `.logs-bar` | `margin-top: 10px` |
| `.logs-toggle` | bouton transparent, bordure `var(--border)`, texte `var(--muted)` 12px, padding `4px 10px`, radius 8px. `:hover:not(:disabled)` → texte `var(--text)`, bordure `var(--accent)`. `:disabled` → `opacity: 0.7` |

### 4.2 Panneaux

| Classe | Rendu |
|---|---|
| `.panel` | fond `var(--panel)`, bordure 1px `var(--border)`, radius 10px, padding 14px, `flex column; min-height: 0; overflow: hidden`, ombre `0 1px 3px rgba(0,0,0,0.28)` |
| `.panel h2` | voir §1.3 (13px uppercase, `var(--title)`, `margin: 0 0 10px`) |
| `.panel-header-btn` | bouton d'en-tête repliable (UI5) : flex `gap: 8px`, `width: 100%`, transparent, sans bordure, `margin: 0 0 10px`, texte hérité aligné à gauche. `:hover h2` → `var(--text)` |
| `.panel-header-btn h2` | `margin: 0` |
| `.panel-caret` | `var(--muted)`, 11px, `flex: 0 0 auto` |
| `.panel.panel-collapsed .panel-header-btn` | `margin-bottom: 0` |
| `.panel-body` | `flex column; min-height: 0; overflow: auto` |

### 4.3 Setup (formulaire projet) & boutons

| Classe | Rendu |
|---|---|
| `.setup` | `width: 560px; gap: 10px` |
| `.setup input, .setup textarea, .chat-input textarea` | fond `var(--panel-2)`, bordure `var(--border)`, radius 8px, texte `var(--text)`, padding 10px, `font: inherit`, `resize: vertical` |
| `.autospec-toggle` | flex `gap: 10px; align-items: flex-start`, 13px `var(--muted)`, `cursor: pointer` |
| `button.primary` | fond+bordure `var(--accent)`, texte `#fff`, `font-weight: 600` |
| `button.danger` | fond transparent, bordure+texte `var(--red)` |
| `button.ghost` | fond transparent |
| `.setup-btn` | `margin-top: 8px`, 12px, padding `6px 10px` |

### 4.4 Chat

| Classe | Rendu |
|---|---|
| `.chat` | `flex: 1` |
| `.chat-header` | flex space-between, `gap: 12px`, `flex-wrap: wrap` |
| `.spec-mode-switch` | segmented control : `inline-flex`, bordure `var(--border)`, radius 8px, `overflow: hidden`, fond `var(--panel-2)` |
| `.spec-mode-btn` | transparent sans bordure, `var(--muted)` 12px, padding `4px 10px`, transition `background 0.15s, color 0.15s`. `+ .spec-mode-btn` → `border-left: 1px solid var(--border)`. `:hover` → `var(--text)`. `.active` → fond `var(--accent)`, texte `#fff` |
| `.brainstorm-offer` | encart B-IDEA : `margin: 8px 0`, padding `10px 12px`, bordure `var(--accent)`, radius 8px, fond `var(--panel-2)` |
| `.brainstorm-offer p` | `margin: 0 0 8px`, 13px, `line-height: 1.4` |
| `.brainstorm-tech` | `var(--muted)` |
| `.brainstorm-actions` | flex `gap: 8px; flex-wrap: wrap` |
| `.brainstorm-btn` | bordure `var(--border)`, radius 6px, padding `6px 12px`, 12px, fond `var(--panel)`. `.accept` → bordure+fond `var(--accent)`, texte `#fff`. `:hover` → bordure `var(--accent)` |
| `.chat-messages` | `flex: 1; overflow-y: auto`, colonne `gap: 8px`, `padding-right: 4px` |
| `.msg` | fond `var(--panel-2)`, bordure `var(--border)`, radius 8px, padding `8px 10px` |
| `.msg pre` | `margin: 4px 0 0`, `white-space: pre-wrap; word-break: break-word`, `font: 13px/1.45 inherit` |
| `.msg-role` | 11px `var(--muted)` uppercase, `letter-spacing: 0.05em` |
| `.msg-user/-pm/-po/-dev/-architect/-critic/-judge/-system` | `border-left: 3px solid <couleur agent>` (voir §2.1) |
| `.chat-input` | flex `gap: 8px; margin-top: 10px` ; son `textarea` → `flex: 1` |

### 4.5 Board (colonnes epics / stories)

| Classe | Rendu |
|---|---|
| `.board .epics` | flex row, `gap: 12px`, `overflow-x: auto`, `flex: 1`, `align-items: flex-start` |
| `.placeholder` | `var(--muted)` ; `.placeholder.small` → 11px, `margin: 2px 0` |
| `.board-empty`, `.chat-empty` | états vides (UI6) : flex colonne centrée, `gap: 10px`, `text-align: center`, padding `24px 16px`, `flex: 1; min-height: 0` ; leur `.placeholder` → `max-width: 38ch; line-height: 1.5` |
| `.epic` | fond `var(--panel-2)`, bordure `var(--border)`, radius 10px, padding 10px, `min-width: 280px; max-width: 340px` |
| `.epic-head` | flex space-between, 11px `var(--muted)` |
| `.epic-title` | `font-weight: 600; margin: 4px 0 10px` |
| `.stories` | flex colonne `gap: 8px` |
| `.story` | carte : fond `var(--panel)`, bordure `var(--border)`, radius 8px, padding `8px 10px`, `cursor: pointer` |
| `.story-head` | flex space-between, `align-items: center` |
| `.drag-handle` | `var(--muted)`, `cursor: grab`, 13px, `line-height: 1`, `margin-right: 6px`, `user-select: none`. `:active` → `cursor: grabbing` |
| `.story.drag-over` | bordure `var(--accent)`, fond `#1a2740` |
| `.story-id` | 11px `var(--muted)` |
| `.story-title` | 13px, `margin-top: 3px` |
| `.story-deps` | 11px `var(--muted)`, `margin-top: 4px` |
| `.story-details` | `margin-top: 8px`, 12px `var(--muted)` ; `h4` → `margin: 8px 0 4px`, `var(--text)` 12px |
| `.gherkin`, `.error-output` | bloc code : fond `#11141b`, bordure `var(--border)`, radius 6px, padding 8px, `white-space: pre-wrap`, `Consolas, monospace` 11px, texte `#c6d4f0` ; `.error-output` → texte `var(--red)` |
| `.test-plan` | `margin: 4px 0; padding-left: 18px` ; `li` → `margin-bottom: 3px` |
| `.test-layer` | tag inline : 10px Consolas, padding `1px 6px`, radius 6px, bordure+texte `var(--accent)`, `margin-right: 4px` |
| `.test-mocks` | `var(--muted)`, italique |
| `.story-right` | flex `align-items: center; gap: 6px` |
| `.story.status-in_progress` | bordure `var(--accent)` + animation `dev-glow` |
| `.story.status-red` | bordure `var(--red)` |
| `.story.status-done` | bordure `var(--green)` |
| `.story.status-failed` | bordure `var(--red)`, fond `#2a1418` |
| `.prio` | 10px Consolas, padding `2px 6px`, radius 6px, bordure `var(--border)`, `var(--muted)`. `.prio-1` → rouge ; `.prio-2` → ambre (bordure+texte) |

### 4.6 Édition de story

| Classe | Rendu |
|---|---|
| `.story-toolbar` | flex `gap: 6px; margin-bottom: 6px` |
| `.small-btn` | padding `4px 8px`, 11px |
| `button.action-btn` | transparent, bordure+texte `var(--accent)` ; `.action-done` → `var(--green)` |
| `.add-story-btn` | `margin-top: 8px; width: 100%`, `border-style: dashed`, 12px, padding `6px 10px` |
| `.story-editor`, `.add-story-form` | flex colonne `gap: 8px` ; `.add-story-form` en plus : `margin-top: 8px`, fond `var(--panel)`, bordure `var(--border)`, radius 8px, padding 10px |
| `.edit-field` | flex colonne `gap: 3px` ; `> span` → 11px `var(--muted)` uppercase `letter-spacing: 0.05em` |
| `.edit-field input/textarea`, `.edit-criterion-row input` | fond `var(--panel-2)`, bordure `var(--border)`, radius 6px, texte `var(--text)`, padding `7px 9px`, `font: inherit` 12px |
| `.edit-field textarea` | `resize: vertical` ; `.mono` → Consolas 11px |
| `.edit-field input[type="number"]` | `width: 90px` |
| `.edit-criteria` | flex colonne `gap: 6px` |
| `.edit-criterion-row` | flex `gap: 6px; align-items: center` ; `input` → `flex: 1` |
| `.edit-actions` | flex `gap: 8px; margin-top: 2px` |
| `.edit-error` | `var(--red)` 11px |

### 4.7 Barre projets (chips multi-projets)

| Classe | Rendu |
|---|---|
| `.project-bar` | flex `align-items: center; gap: 8px`, padding `8px 18px`, `border-bottom: 1px solid var(--border)`, fond `var(--panel)`, `overflow-x: auto` |
| `.project-select` | flex `gap: 6px`, `flex: 0 0 auto`, `padding-right: 10px; margin-right: 2px`, `border-right: 1px solid var(--border)` |
| `.project-select-icon` | 15px |
| `.project-select select` | fond `var(--panel-2)`, bordure `var(--border)`, radius 8px, padding `6px 10px`, 13px `font-weight: 600`, `max-width: 280px`, pointer. `:hover` / `:focus-visible` → bordure `var(--accent)` (focus : `outline: none`) |
| `.project-chip` | pill : flex `gap: 7px`, padding `5px 8px 5px 10px`, bordure `var(--border)`, `border-radius: 99px`, fond `var(--panel-2)`, pointer, `white-space: nowrap`, 13px. `.active` → bordure `var(--accent)`, fond `#1a2740`. `.archived` → `opacity: 0.55`, `border-style: dashed` (`:hover` → opacity 0.8) |
| `.project-chip .dot` | pastille `8px × 8px`, `border-radius: 50%`, inline-block |
| `.dot.pulse` | animation `chip-pulse 1.2s ease-in-out infinite` |
| `.chip-del` | bouton nu : `var(--muted)`, padding `0 2px`, 12px, `line-height: 1`. `:hover` → `var(--red)` |
| `.chip-archive` | idem 11px, pointer. `:hover` → `var(--accent)` |
| `.chip-progress` | 10px `var(--muted)` Consolas |
| `.chip-play` | bouton nu `var(--muted)`, padding `0 2px`, 12px. `:hover` → `var(--accent)` |
| `.chips-hint` | `var(--muted)` 12px nowrap, padding `0 4px`, `flex: 0 0 auto` |
| `.archived-toggle` | pill transparent, bordure `var(--border)`, `var(--muted)`, `border-radius: 99px`, padding `4px 10px`, 12px nowrap. `:hover` → texte `var(--text)` + bordure accent. `.active` → idem + fond `#1a2740` |
| `.project-new` | transparent, `border-style: dashed`, nowrap |
| `.rollback-iters` | flex wrap `gap: 8px; margin-top: 12px` ; `button` → `min-width: 110px` |
| `.error-banner` | fond `#2a1418`, `border-bottom: 1px solid var(--red)`, texte `var(--red)`, padding `8px 18px`, 13px |

### 4.8 Critères d'acceptation

| Classe | Rendu |
|---|---|
| `.criteria` | flex colonne `gap: 6px` |
| `.criterion` | bordure `var(--border)`, radius 8px, fond `var(--panel-2)`, `overflow: hidden` |
| `.criterion-head` | flex `gap: 8px`, padding `7px 10px`, pointer |
| `.criterion-text` | `flex: 1`, 12px `var(--text)` |
| `.criterion-expander` | `var(--muted)` 11px |
| `.state-dot` | 12px, `line-height: 1` |
| `.state-tag` | 10px, padding `2px 8px`, `border-radius: 99px`, bordure `var(--border)`, nowrap |
| `.state-green` | `var(--green)` ; `.state-tag.state-green` → bordure verte |
| `.state-red` | `var(--red)` ; `.state-tag.state-red` → bordure rouge |
| `.state-nonexistent` | `var(--muted)` |
| `.criterion-body` | padding `4px 10px 10px`, `border-top: 1px solid var(--border)` ; `h5` → `margin: 8px 0 4px`, 11px muted uppercase `0.05em` |
| `.criterion-tests` | liste nue, flex colonne `gap: 5px` ; `li` → flex `gap: 6px`, 12px |
| `.test-desc` | `flex: 1`, `var(--text)` |

### 4.9 Badges génériques

| Classe | Rendu |
|---|---|
| `.badge` | 10px, padding `2px 8px`, `border-radius: 99px`, bordure `var(--border)`, nowrap |
| `.badge-todo` | texte `var(--muted)` |
| `.badge-in_progress` | texte+bordure `var(--accent)` |
| `.badge-red` | texte+bordure `var(--red)` |
| `.badge-green`, `.badge-done` | texte+bordure `var(--green)` |
| `.badge-failed` | texte `#fff`, fond+bordure `var(--red)` |
| `.badge-btn` | badge cliquable (O2) : pointer, fond transparent, `font: inherit`, inline-flex `gap: 4px`. `:hover` → bordure `var(--accent)` |
| `.quality-badge` | inline-flex `gap: 3px`, `margin-left: 6px`, padding `1px 6px`, radius 10px, fond `var(--panel-2)`, bordure `var(--border)`, texte `var(--amber)` 10px bold, nowrap |
| `.mutation-badge` | idem quality-badge mais texte `var(--accent)` (Q1) |
| `.coverage-badge` | idem mais texte `#3fb950` (Q2) |
| `.badge-technical` | inline-flex `gap: 2px`, 10px bold, padding `1px 6px`, radius 10px, fond `#2a2140`, texte `#c9b8f0`, bordure `#4a3d72` |

### 4.10 Backlog / hypothèses

| Classe | Rendu |
|---|---|
| `.backlog` | `max-height: 280px` |
| `.hypotheses` | `overflow-y: auto`, flex colonne `gap: 6px` |
| `.hypothesis` | flex `gap: 8px`, fond `var(--panel-2)`, bordure `var(--border)`, radius 8px, padding `6px 10px`, 12px |
| `.hyp-selected` | bordure `var(--accent)` |
| `.hyp-rank` | `var(--muted)` Consolas |
| `.hyp-title` | `flex: 1` |
| `.hyp-scores` | `var(--muted)` Consolas 11px |
| `.badge-hyp-selected` | texte+bordure `var(--accent)` |
| `.badge-hyp-proposed` | `var(--muted)` |
| `.badge-hyp-rejected` | `var(--red)` |
| `.hyp-shipped` | 11px `var(--muted)`, `margin-top: 4px` |

### 4.11 Panneau Exécution (run)

| Classe | Rendu |
|---|---|
| `.run-header` | flex `gap: 14px`, wrap ; `h2` → margin 0 |
| `.run-buttons` | `margin-left: auto`, flex `gap: 8px` |
| `.run-args` | input : fond `var(--panel-2)`, bordure `var(--border)`, radius 8px, padding `7px 10px`, 12px, `width: 170px`. `:focus-visible` → `outline: none`, bordure accent |
| `.run-menu-wrap` | `position: relative` (UI7 : menu overflow) |
| `.run-menu` | popover : `position: absolute; right: 0; top: calc(100% + 6px); z-index: 30`, flex colonne, `min-width: 210px`, fond `var(--panel)`, bordure, radius 10px, padding 6px, ombre `0 10px 28px rgba(0,0,0,0.45)` ; `button` → transparent sans bordure, aligné gauche, padding `8px 10px`, radius 6px, 13px ; `:hover` → fond `var(--panel-2)` |
| `.phase` | pill : 12px, padding `3px 10px`, radius 99px, bordure `var(--border)`, `var(--muted)`. `.phase-build` → accent ; `.phase-done` → vert ; `.phase-error` → rouge (texte+bordure) |
| `.usage-meter` | 11px `var(--muted)` nowrap, `font-variant-numeric: tabular-nums`. `.over-budget` → `var(--red)`, bold 600 |
| `.resume-banner` | pill ambre (M2) : inline-flex `gap: 6px`, 11px, texte+bordure `var(--amber)`, radius 99px, padding `2px 6px 2px 10px`, nowrap ; `.small-btn` interne → padding `1px 6px`, 10px, `line-height: 1.4` |
| `.logs` | console : `flex: 1; overflow-y: auto`, fond `#11141b`, bordure, radius 8px, `margin-top: 10px`, padding 8px, Consolas 12px |
| `.log-line` | `white-space: pre-wrap; word-break: break-word` |
| `.log-source` | `var(--accent)` |
| `.run-error` | `#e06c75`, `0.85rem`, `margin-left: 0.5rem`, pre-wrap + break-word |

### 4.12 Code viewer (overlay plein écran)

| Classe | Rendu |
|---|---|
| `.code-viewer-btn` | `align-self: flex-start`, 12px, padding `6px 12px` |
| `.code-viewer-overlay` | `position: fixed; inset: 0`, fond `rgba(0,0,0,0.6)`, flex centré, `z-index: 100`, padding 24px |
| `.code-viewer-panel` | fond `var(--panel)`, bordure, radius 12px, `width: min(1100px, 92vw); height: min(720px, 88vh)`, flex colonne, `overflow: hidden` |
| `.code-viewer-header` | flex space-between, padding `10px 14px`, `border-bottom`, fond `var(--panel-2)` |
| `.code-viewer-title` | 13px uppercase `letter-spacing: 0.06em`, `var(--muted)` |
| `.code-viewer-close` | padding `4px 10px`, 13px, `line-height: 1` |
| `.code-viewer-body` | `flex: 1; min-height: 0`, `display: grid; grid-template-columns: 260px 1fr` |
| `.code-viewer-files` | `border-right: 1px solid var(--border)`, `overflow-y: auto`, padding 8px, flex colonne `gap: 2px` |
| `.code-viewer-file` | bouton fichier : aligné gauche, transparent, `border: 1px solid transparent`, radius 6px, padding `5px 8px`, Consolas 12px, ellipsis. `:hover` → fond `var(--panel-2)`. `.active` → fond `#1a2740`, bordure+texte `var(--accent)` |
| `.code-viewer-content` | `min-width: 0; overflow: auto`, padding `10px 12px`, flex colonne `gap: 6px` |
| `.code-viewer-pre` | pre : `margin: 0; flex: 1`, fond `#11141b`, bordure, radius 8px, padding 12px, Consolas 12px `line-height: 1.5`, texte `#c6d4f0`, `white-space: pre; overflow: auto` |
| `.code-viewer-muted` | `var(--muted)` 12px |
| `.code-viewer-error` | `var(--red)` 12px, break-word |
| `.code-viewer-truncated` | `var(--amber)` 11px |

### 4.13 Diff viewer (overlay par story)

Mêmes patterns que le code viewer : `.diff-overlay` (identique à `.code-viewer-overlay`), `.diff-panel` (`width: min(1000px, 92vw); height: min(700px, 88vh)`), `.diff-header` / `.diff-title` / `.diff-close` (identiques aux équivalents code-viewer), `.diff-content` (`flex: 1; min-height: 0; overflow: auto; padding: 10px 12px; flex column`), `.diff-pre` (identique à `.code-viewer-pre`).

| Classe | Rendu |
|---|---|
| `.diff-add` | `var(--green)` |
| `.diff-del` | `var(--red)` |
| `.diff-muted` | `var(--muted)` 12px |
| `.diff-error` | `var(--red)` 12px, break-word |

### 4.14 Langage backend (L2) & Architecture

| Classe | Rendu |
|---|---|
| `.language-scores` | flex `gap: 14px`, 12px `var(--muted)`, `margin-bottom: 6px` |
| `.language-rationale` | 12px `var(--muted)`, `margin: 0 0 10px`, `line-height: 1.5` |
| `.language-override` | flex `gap: 8px`, 12px `var(--muted)` ; `select` → fond `var(--panel-2)`, bordure, radius 8px, padding `5px 8px`, 13px |
| `.architecture` | flex colonne `gap: 8px` |
| `.architecture .plan-quality` | 13px `var(--muted)` ; `strong` → `var(--green)` |
| `.architecture-design` | bloc code : fond `#11141b`, bordure, radius 6px, padding 8px, `max-height: 320px; overflow: auto`, `white-space: pre`, Consolas 11px `line-height: 1.5`, texte `#c6d4f0` |

### 4.15 Graphe de dépendances (DAG)

| Classe | Rendu |
|---|---|
| `.dag-panel` | flex colonne `gap: 8px` |
| `.dag-summary` | 12px `var(--muted)` |
| `.dag-scroll` | `overflow: auto; max-height: 560px`, bordure, radius 8px, fond `#0e1117` |
| `.dag-svg` | `display: block` |
| `.dag-edge` | `stroke: #3a4055; stroke-width: 1.5` |
| `.dag-edge-crit` | `stroke: #e0b341; stroke-width: 2.5` (chemin critique) |
| `.dag-node` | pointer ; `rect` → `stroke: var(--border); stroke-width: 1; fill: #1a1f2b` ; `:hover rect` → `filter: brightness(1.25)` |
| `.dag-node-crit rect` | `stroke: #e0b341; stroke-width: 2` |
| `.dag-node-id` | `fill: #e6ecf7`, 11px bold Consolas |
| `.dag-node-title` | `fill: var(--muted)`, 10px |
| `.dag-node-done rect` | `fill: #16321f; stroke: var(--green)` |
| `.dag-node-in_progress rect` | `fill: #16233a; stroke: #4a8fe0` |
| `.dag-node-failed rect` | `fill: #3a1a1a; stroke: #e06c6c` |
| `.dag-node-red rect` | `fill: #3a2a16; stroke: #e0a341` |
| `.dag-node-blocked rect` | `fill: #2a2316; stroke: #8a7a4a` |
| `.dag-node-ready rect` | `fill: #1a1f2b; stroke: #5a6680` |

### 4.16 Technical Story & revue de plan

| Classe | Rendu |
|---|---|
| `.story-ts-lineage` | 11px `var(--muted)`, `margin-bottom: 6px` |
| `.story-ts-contract-heading` | 12px bold `#c9b8f0`, `margin: 6px 0 4px` |
| `.plan-review-score` | 13px `var(--muted)`, `margin-bottom: 6px` ; `strong` → 14px |
| `.plan-review-score-good strong` | `var(--green)` |
| `.plan-review-score-mid strong` | `#e0b341` |
| `.plan-review-score-low strong` | `var(--red, #e06c6c)` |
| `.plan-review-block` | `margin-top: 8px` |
| `.plan-review-heading` | 12px bold `var(--muted)` uppercase `0.03em`, `margin-bottom: 4px` |
| `.plan-review-list` | liste nue `padding-left: 4px`, flex colonne `gap: 4px` ; `li` → 12px `line-height: 1.45`, `#c6d4f0` |
| `.plan-review-issues li` | `#e6b8b8` |
| `.plan-review-clean` | 12px `var(--green)` |

### 4.17 Modales

| Classe | Rendu |
|---|---|
| `.modal-backdrop` | `position: fixed; inset: 0`, fond `rgba(0,0,0,0.6)`, flex centré, `z-index: 120`, padding 24px |
| `.modal` | `position: relative`, fond `var(--panel)`, bordure, radius 12px, padding 10px, `max-width: 92vw; max-height: 88vh; overflow: auto` ; `.modal .setup` → `border: none` |
| `.modal-close` | `position: absolute; top: 10px; right: 10px`, padding `3px 9px`, 13px, `line-height: 1`, `z-index: 1` |

### 4.18 Provider d'agents (M1 / UI10)

| Classe | Rendu |
|---|---|
| `.provider-select` | flex `gap: 6px`, 12px `var(--muted)` ; `select` → fond `var(--panel-2)`, bordure, radius 8px, padding `5px 8px`, 12px |
| `.provider-model` | Consolas 11px, `max-width: 180px`, ellipsis |
| `.provider-model-select` | fond `var(--panel-2)`, bordure, radius 8px, Consolas 11px, padding `5px 8px`, `max-width: 200px` |
| `.provider-control` | `position: relative` |
| `.provider-trigger` | pilule : inline-flex `gap: 6px`, fond `var(--panel-2)`, bordure, `border-radius: 99px`, padding `5px 12px`, 12px, pointer, `max-width: 260px`. `:hover:not(:disabled)` → bordure accent. `:disabled` → `cursor: default`, texte muted |
| `.provider-trigger-model` | Consolas `var(--muted)`, `max-width: 150px`, ellipsis |
| `.provider-caret` | `var(--muted)` 10px |
| `.provider-menu` | popover : absolute `right: 0; top: calc(100% + 6px); z-index: 30`, flex colonne `gap: 10px`, `min-width: 240px`, fond `var(--panel)`, bordure, radius 10px, padding 12px, ombre `0 10px 28px rgba(0,0,0,0.45)` |
| `.provider-field` | flex colonne `gap: 4px`, 11px muted uppercase `0.05em` ; `select` → panel-2, radius 8px, padding `6px 8px`, 13px |
| `.provider-hint` | annule l'uppercase (normal, `letter-spacing: 0`), `var(--muted)` ; `.provider-hint-live` → `var(--green)` |
| `.provider-refresh` | bouton nu : `margin-left: 6px`, padding `0 4px`, 11px, `opacity: 0.8`. `:hover` → 1 ; `:disabled` → 0.4 |

### 4.19 Composants du produit (E3/E4)

| Classe | Rendu |
|---|---|
| `.components` | `max-height: 260px` |
| `.component-list` | `overflow-y: auto`, flex colonne `gap: 6px` |
| `.component` | flex `gap: 8px`, fond `var(--panel-2)`, bordure, radius 8px, padding `6px 10px`, 12px ; `.status-rejected` → `opacity: 0.55` |
| `.component-name` | `flex: 1; min-width: 0` |
| `.component-tech` | `var(--muted)` |
| `.component-optional` | `var(--amber)` 11px |
| `.component-status-approved` | texte+bordure `var(--accent)` |
| `.component-status-created` | texte+bordure `var(--green)` |
| `.component-status-rejected` | texte `var(--red)` |

### 4.20 Navigation board (drill-down, fil d'Ariane, vues)

| Classe | Rendu |
|---|---|
| `.board-top` | flex `align-items: baseline; gap: 14px`, wrap |
| `.breadcrumb` | flex `gap: 6px`, 12px |
| `.breadcrumb .crumb` | bouton nu `var(--accent)`, padding `2px 4px`, radius 4px, 12px. `:hover:not(:disabled)` → fond `var(--panel-2)` + underline. `:disabled` → muted. `.current` → `var(--text)` bold 600 |
| `.breadcrumb .crumb-sep` | `var(--muted)` |
| `.epic-grid` | flex wrap `gap: 12px`, `align-content: flex-start`, `overflow-y: auto; flex: 1`, `padding-top: 4px` (évite le rognage du lift hover -1px et de l'outline focus offset 2px) |
| `.epic-iter` | 11px `var(--muted)` nowrap |
| `.epic-iter-link` | pill : fond `var(--panel-2)`, bordure, `border-radius: 999px`, texte `var(--accent)`, padding `1px 8px`, 11px. `:hover` → bordure accent + fond `#1a2740` |
| `.view-toggle` | segmented « Vision produit / Itérations » : inline-flex, `align-self: flex-start`, **`flex-shrink: 0`** (sinon compressé verticalement dans une colonne flex bornée), bordure, radius 8px, `overflow: hidden`, fond `var(--panel-2)` ; `button` → transparent, muted 13px, padding `6px 14px`, transitions 0.15s ; `+ button` → `border-left` ; `:hover` → text ; `.active` → fond accent, `#fff`, bold 600 |
| `.epic-card` | pointer, `transition: border-color 0.12s ease, transform 0.12s ease`. `:hover` → bordure accent + `transform: translateY(-1px)`. `:focus-visible` → `outline: 2px solid var(--accent); outline-offset: 2px` |
| `.epic-desc` | 12px `var(--muted)`, `margin: 0 0 8px` |
| `.epic-card-meta` | 11px `var(--muted)`, `margin-bottom: 4px` ; `.epic-meta-working` → accent ; `.epic-meta-failed` → rouge |
| `.epic-head-right` | flex `gap: 6px` |
| `.epic-card.epic-done` | bordure `var(--green)` |
| `.epic-card.epic-failed` | bordure `var(--red)` |
| `.epic-card.epic-working` | bordure accent + animation `dev-glow 1.6s` |
| `.epic-view.epic-working .epic-view-title` | `var(--accent)` |

### 4.21 Vue Itérations (timeline)

| Classe | Rendu |
|---|---|
| `.iter-hint` | 11px `var(--muted)` |
| `.iter-timeline` | flex colonne `gap: 12px`, `overflow-y: auto; flex: 1` |
| `.iter-card` | bordure `var(--border)` + `border-left: 3px solid var(--border)`, radius 10px, fond `var(--panel-2)`, padding 12px. `.epic-working` → border-left accent ; `.epic-done` → vert ; `.epic-failed` → rouge. `.focused` → `box-shadow: 0 0 0 2px var(--accent)` |
| `.iter-card-head` | flex `gap: 12px`, wrap |
| `.iter-num` | flex `gap: 7px`, bold 600, 14px |
| `.iter-state` | 12px `var(--muted)`. `.state-working` → accent ; `.state-done` → vert ; `.state-failed` → rouge |
| `.iter-counts` | `margin-left: auto`, 12px muted |
| `.iter-usage` | `margin-top: 8px`, 12px muted Consolas |
| `.iter-card-actions` | `margin-top: 10px`, flex `justify-content: flex-end` |
| `.iter-epics` | flex wrap `gap: 6px`, `margin: 10px 0 4px` |
| `.iter-epic-chip` | fond `var(--panel)`, bordure, radius 6px, padding `3px 8px`, 12px, pointer. `:hover` → bordure accent |
| `.iter-stories` | liste nue, `margin: 6px 0 0`, flex colonne `gap: 6px` |
| `.iter-story-chip` | bouton pleine largeur aligné gauche : flex `gap: 8px`, fond `var(--panel)`, bordure, radius 6px, padding `6px 8px`, pointer, `font: inherit`. `:hover` → bordure accent |
| `.iter-story-id` | 11px muted, `flex: 0 0 auto` |
| `.iter-story-title` | 13px, `flex: 1`, ellipsis |

### 4.22 Progression d'epic, spinner, vues détail

| Classe | Rendu |
|---|---|
| `.epic-progress` | barre : `height: 6px`, fond `var(--panel)`, bordure, radius 99px, `overflow: hidden`, `margin: 8px 0 6px` |
| `.epic-progress-fill` | `height: 100%`, radius 99px, fond `var(--accent)`, `transition: width 0.3s ease`. `.state-done` → vert ; `.state-failed` → rouge ; `.state-pending` → `var(--muted)` |
| `.spinner` | `12px × 12px`, `border: 2px solid var(--border)` avec `border-top-color: var(--accent)`, `border-radius: 50%`, inline-block, `animation: spin 0.7s linear infinite` |
| `.spinner-sm` | `9px × 9px`, `border-width: 1.5px`, `margin-right: 3px`, `vertical-align: -1px` |
| `.epic-view`, `.us-view` | `overflow-y: auto; flex: 1` |
| `.epic-view-title` | `margin: 6px 0 4px` |
| `.epic-view-desc` | 13px muted, `margin: 0 0 10px` |
| `.story-open-hint` | 10px muted, `margin-top: 6px`, `text-align: right` |
| `.story-detail` | 13px ; `> p` → `var(--muted)` |
| `.story-detail-head` | flex space-between, `gap: 8px` |
| `.story-detail-title` | `margin: 6px 0 8px`, 16px |

### 4.23 Toasts (U3) & bannières

| Classe | Rendu |
|---|---|
| `.toasts` | conteneur : `position: fixed; right: 16px; bottom: 16px`, flex colonne `gap: 8px`, `z-index: 1000`, `max-width: 340px` |
| `.toast` | flex `align-items: flex-start; gap: 8px`, padding `10px 12px`, radius 8px, fond `var(--panel-2)`, bordure + `border-left: 3px solid var(--accent)`, ombre `0 4px 14px rgba(0,0,0,0.35)`, 12px, `animation: toast-in 0.18s ease` |
| `.toast-success` / `.toast-warning` / `.toast-error` / `.toast-info` | border-left `#3fb950` / `#d29922` / `#e06c75` / `var(--accent)` |
| `.toast-text` | `flex: 1` ; `.toast-title` → bold 600 ; `.toast-body` → muted, `margin-top: 2px`, break-word |
| `.toast-close` | bouton nu muted, padding `0 2px`, 12px. `:hover` → `var(--text)` |
| `.approval-banner` | (U4) inline-flex `gap: 8px`, `margin-left: 8px`, padding `2px 8px`, radius 6px, fond `#2b2410`, bordure+texte `#d29922`, 12px bold |
| `.approve-btn` | texte `#3fb950` |
| `.regression-banner` | (R2) inline-flex, `margin-left: 8px`, padding `2px 8px`, radius 6px, fond `#2b1416`, bordure+texte `#e06c75`, 12px bold |

### 4.24 Dashboard usine (U2) & coût

| Classe | Rendu |
|---|---|
| `.dash-btn` | fond `var(--panel-2)`, bordure, radius 6px, padding `4px 9px`, 14px, `margin-left: auto`. `:hover` → bordure accent |
| `.dashboard` | `max-width: 760px; width: 92%` |
| `.dashboard-head` | flex space-between centré |
| `.metrics-grid` | `display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; margin-top: 12px` |
| `.metric-card` | fond `var(--panel-2)`, bordure, radius 8px, padding `12px 10px`, `text-align: center` |
| `.metric-value` | 18px bold 700 `var(--accent)` |
| `.metric-label` | 11px muted, `margin-top: 4px` |
| `.forecast-meter` | (O2) `margin-left: 8px`, padding `1px 6px`, radius 10px, fond `var(--panel-2)`, bordure, muted 11px |

### 4.25 Multi-stream (ST-12/13/14)

| Classe | Rendu |
|---|---|
| `.stream-badge` | inline-flex `gap: 3px`, padding `1px 7px`, radius 10px, 11px bold, bordure `var(--border)`, fond `var(--panel-2)`, `var(--text)`, nowrap |
| `.stream-badge-backend/-frontend/-cache/-database/-other` | couleurs §2.4 |
| `.stream-filter` | flex wrap `gap: 6px`, `margin: 6px 0 4px` ; `button` → pill padding `2px 10px`, radius 12px, 12px, panel-2, muted. `.active` → bordure accent, texte `var(--text)`, fond `rgba(79,140,255,0.12)` |
| `.blocked-badge` | inline-flex `gap: 3px`, padding `1px 7px`, radius 10px, 11px bold, bordure `var(--red)`, texte `#ffb4b4`, fond `rgba(255,90,90,0.08)`, nowrap |
| `.merge-badge` | idem, bordure `var(--border)`. `.merge-ok` → bordure verte, texte `#b6f0c0` ; `.merge-conflict` → bordure rouge, texte `#ffb4b4`, fond `rgba(255,90,90,0.08)` |
| `.story-row-hints` | flex wrap `gap: 6px; margin-top: 4px` ; `:empty` → `display: none` |
| `.task-list` | `margin-top: 6px`, `border-top: 1px dashed var(--border)`, `padding-top: 6px` |
| `.task-list-toggle` | bouton nu muted 12px, `padding: 0 0 4px` |
| `.tasks` | flex colonne `gap: 5px` |
| `.task-row` | flex wrap centré `gap: 6px`, padding `5px 8px`, bordure, radius 7px, fond `var(--panel-2)`, pointer. `:hover` → bordure accent. `.status-in_progress` → bordure accent + `dev-glow` |
| `.task-id` | `font-family: var(--mono, monospace)` 11px muted |
| `.task-title` | `flex: 1`, 13px, `min-width: 80px` |
| `.us-tasks` | `margin-bottom: 10px` |
| `.task-criteria` | `margin: 4px 0; padding-left: 18px` |

### 4.26 Stepper (B-UX : suivi d'étapes par work item)

| Classe | Rendu |
|---|---|
| `.stepper` | `flex: 1; min-width: 0`, flex colonne `gap: 3px` |
| `.stepper.stepper-stale` | `opacity: 0.5; filter: grayscale(0.4)` (tick périmé > 25 s) |
| `.stepper-track` | liste nue, flex `align-items: flex-start; gap: 2px` |
| `.stepper-cell` | `flex: 1; min-width: 0`, flex colonne centrée `gap: 2px`, `position: relative`, 10px muted |
| `.stepper-cell::before` | barre de liaison : `content: ""`, absolute `top: 5px; left: -50%`, `width: 100%; height: 2px`, fond `var(--border)`, `z-index: 0` ; masquée sur `:first-child` |
| `.stepper-dot` | `11px × 11px`, `border-radius: 50%`, fond `var(--stage-queued)`, `border: 2px solid var(--panel)`, `z-index: 1` |
| `.stepper-cell-label` | nowrap + ellipsis, `max-width: 100%` |
| `.stepper-elapsed` | Consolas 9px `var(--amber)` |
| `.stepper-done` | dot fond `var(--stage-done)` ; label `var(--stage-done)` |
| `.stepper-active` | dot fond `var(--stage-active)` + `box-shadow: 0 0 0 3px rgba(79,140,255,0.25)` ; label `var(--stage-active)` bold 600 |
| `.stepper-failed` | dot fond `var(--stage-failed)` + `animation: attention-pulse 1.3s ease-in-out infinite` ; label `var(--stage-failed)` bold 600 |
| `.stepper-recovery` | 11px `var(--amber)` |

### 4.27 Vue Activité canonique (P6)

| Classe | Rendu |
|---|---|
| `.activity` | `flex: 1` |
| `.activity-header` | flex `gap: 12px`, wrap, `margin-bottom: 10px` ; `h2` → margin 0 |
| `.activity-counts` | flex `gap: 6px`, wrap |
| `.count-chip` | pill 11px, padding `2px 9px`, radius 99px, bordure `var(--border)`, muted, nowrap. `.count-running` / `.count-done` / `.count-failed` → texte+bordure `--status-running/done/failed` |
| `.attention-chip` | pill persistant : 12px bold 700, padding `3px 10px`, radius 99px, texte `#fff`, fond+bordure `var(--attention)`, nowrap, `animation: attention-pulse 1.3s` |
| `.stall-reason` | 12px `var(--amber)`, bordure ambre, radius 99px, padding `2px 10px`, nowrap |
| `.approval-banner-scene` | (P13) flex `gap: 10px`, `margin: 0 0 12px`, padding `10px 14px`, 13px, wrap ; `.approval-banner-text` → `flex: 1; min-width: 0` |
| `.activity-body` | flex `gap: 12px; flex: 1; min-height: 0` |
| `.crew-rail` | rail de filtre : `flex: 0 0 auto`, colonne `gap: 6px`, `min-width: 130px` |
| `.crew-rail-toggle` | bouton nu muted 12px aligné gauche, padding `2px 0` |
| `.crew-rail-list` | colonne `gap: 4px` ; `button` → gauche, 12px, padding `4px 8px`, radius 7px, panel-2, muted. `.active` → bordure accent, texte `var(--text)`, fond `rgba(79,140,255,0.12)` |
| `.activity-rows-wrap` | `flex: 1; min-width: 0; overflow-y: auto`, colonne `gap: 12px` |
| `.activity-attention-region` | région épinglée « à traiter » : bordure `var(--attention)`, radius 10px, fond `var(--attention-bg)`, padding `8px 10px`, colonne `gap: 8px` |
| `.activity-region-title` | margin 0, 11px uppercase `0.06em`, `var(--attention)` |
| `.activity-rows` | colonne `gap: 8px` |
| `.activity-row` | bordure, radius 9px, fond `var(--panel-2)`, `padding: var(--row-pad) 10px`. `.activity-row-attention` → bordure `var(--attention)` |
| `.activity-row-main` | flex centré `gap: 8px` |
| `.activity-row-toggle` | bouton nu muted 12px, padding `0 2px` |
| `.activity-row-id` | Consolas 11px muted, `flex: 0 0 auto` |
| `.activity-persona` | 11px `var(--text)`, nowrap, `flex: 0 0 auto` |
| `.activity-row-title` | `font-size: var(--font-sm)`, `flex: 0 1 180px; min-width: 0`, ellipsis |
| `.activity-row-menu-wrap` | `position: relative; flex: 0 0 auto` |
| `.activity-menu` | popover : absolute `right: 0; top: calc(100% + 4px); z-index: 30`, colonne, `min-width: 170px`, fond `var(--panel)`, bordure, radius 10px, padding 6px, ombre `0 10px 28px rgba(0,0,0,0.45)` ; `button` → transparent, gauche, padding `7px 10px`, radius 6px, 13px ; `:hover` → fond panel-2 |
| `.activity-blockers` | `margin-top: 4px`, 11px `#ffb4b4` |
| `.activity-drawer` | `margin-top: 8px`, `border-top: 1px dashed var(--border)`, `padding-top: 8px`, colonne `gap: 10px` |

### 4.28 Chat ciblé par item & consignes (guidance)

| Classe | Rendu |
|---|---|
| `.item-chat` | colonne `gap: 8px` |
| `.guidance-entries` | liste nue, colonne `gap: 5px` |
| `.guidance-entry` | flex centré `gap: 8px`, 12px, padding `5px 8px`, bordure, radius 7px, fond `var(--panel)` |
| `.guidance-text` | `flex: 1; min-width: 0` |
| `.guidance-status` | pill 10px, padding `1px 8px`, radius 99px, bordure `var(--border)`, nowrap. `-queued` → ambre ; `-applied` → vert ; `-too_late` → rouge (texte+bordure) |
| `.item-chat-input` | flex `gap: 8px; align-items: flex-end` ; `textarea` → `flex: 1`, panel-2, bordure, radius 8px, padding 8px, 12px, `resize: vertical` |
| `.extend-criteria` | colonne `gap: 8px` ; `textarea` → mêmes styles que ci-dessus |

### 4.29 Activité LLM (O2, inline)

| Classe | Rendu |
|---|---|
| `.llm-activity` | `margin-top: 10px`, bordure, radius 8px, fond `var(--panel-2)`, padding `8px 10px`. `.llm-muted` → muted 12px |
| `.llm-activity-head` | flex centré `gap: 8px`, `margin-bottom: 6px` |
| `.llm-activity-title` | bold 600, 13px |
| `.llm-activity-count` | `margin-left: auto`, 11px muted, bordure, radius 99px, padding `0 7px` |
| `.llm-live` | 10px `var(--green)`, `animation: llm-pulse 1.6s ease-in-out infinite` |
| `.llm-call-list` | colonne `gap: 6px` |
| `.llm-call` | bordure, radius 6px, `overflow: hidden`, fond `var(--panel)`. `.llm-call-error` → bordure rouge |
| `.llm-call-head` | bouton pleine largeur : flex centré `gap: 8px`, padding `5px 8px`, transparent, sans bordure, 12px, gauche. `:hover` → fond panel-2 |
| `.llm-call-caret` | muted |
| `.llm-call-role` | bold 600 |
| `.llm-call-tokens`, `.llm-call-cost`, `.llm-call-dur`, `.llm-call-time` | 11px muted ; `.llm-call-time` → `margin-left: auto` |
| `.llm-call-badge-error` | 10px `#fff` sur fond `var(--red)`, radius 99px, padding `0 6px` |
| `.llm-call-body` | padding `6px 8px 8px`, `border-top: 1px dashed var(--border)`, colonne `gap: 8px` |
| `.llm-call-section h6` | `margin: 0 0 3px`, 11px uppercase `0.04em`, muted |
| `.llm-trunc` | `var(--red)`, annule uppercase/letter-spacing |
| `.llm-pre` | pre : margin 0, `max-height: 320px; overflow: auto`, fond `#11141b`, bordure, radius 6px, padding 8px, Consolas 12px `line-height: 1.5`, `#c6d4f0`, `pre-wrap` + break-word. `.llm-pre-error` → `var(--red)` |

### 4.30 Fenêtre Settings (thème + langue)

| Classe | Rendu |
|---|---|
| `.settings-modal` | `width: 420px; max-width: 92vw`, padding `18px 18px 20px` ; `h2` → `margin: 0 0 14px`, 18px, `var(--title)` |
| `.settings-section` | `margin-bottom: 18px` ; `:last-child` → 0 |
| `.settings-section > .settings-section-title` | 12px uppercase `0.04em` muted, `margin-bottom: 8px` |
| `.settings-row` | flex space-between centré, `gap: 12px`, `margin-bottom: 6px` |
| `.settings-row-label` | 14px `var(--text)` |
| `.settings-hint` | 12px muted, `margin: 0 0 8px` |
| `.settings-segmented` | inline-flex, bordure, radius 8px, `overflow: hidden`, fond panel-2 ; `button` → transparent muted, padding `6px 12px`, 13px, inline-flex `gap: 6px`. `:hover` → text. **`[aria-pressed="true"]`** → fond accent, `#fff` (état actif piloté par ARIA, pas par classe) |

---

## 5. Responsive (toutes les media queries)

| Media query | Effet |
|---|---|
| `@media (min-width: 1600px)` | `--rail-w: 400px` (rail plus large, feel 3 colonnes) |
| `@media (min-width: 1100px) and (max-width: 1599px)` | `--rail-w: 340px` (2 colonnes, rail resserré) |
| `@media (max-width: 1199px)` | `--font-sm: 12px; --row-pad: 4px` + `[data-density="compact"] .activity-row-title { font-size: var(--font-sm); }` (densité compacte) |
| `@media (max-width: 1099px)` | `--rail-w: 1fr; --scene-w: 1fr` et `.workspace { grid-template-columns: 1fr; }` (mono-colonne, rail empilé au-dessus de la scène) |
| `@media (max-width: 1099px)` (2e bloc, section Activité) | `.activity-body { flex-direction: column; }` et `.crew-rail { flex-direction: row; flex-wrap: wrap; min-width: 0; }` |
| `@media (prefers-reduced-motion: reduce)` ×3 | (1) coupe `dev-glow` sur `.epic-card.epic-working` et `.story.status-in_progress`, `.spinner` ralenti à 1.4s ; (2) coupe l'animation de `.task-row.status-in_progress` ; (3) coupe `.stepper-failed .stepper-dot` et `.attention-chip` |

---

## 6. Logo, favicon & titre

### 6.1 Logo (`Logo.tsx`)

Marque : chevrons de code `< >` autour d'un « spark » IA. Les chevrons héritent de `currentColor` (donc `var(--title)` via `.app-logo`), le spark utilise `var(--accent)` — bicolore et adaptatif au thème. Props : `size?: number` (sinon dimensionné par la classe CSS, `1.35em` dans le header), `className?`. Accessibilité : `role="img"` + `aria-label="Autospec"`.

```tsx
<svg className={`app-logo${className ? ` ${className}` : ""}`}
     width={size} height={size} viewBox="0 0 32 32"
     role="img" aria-label="Autospec" fill="none"
     xmlns="http://www.w3.org/2000/svg">
  {/* code brackets */}
  <path d="M12 8 L5 16 L12 24" stroke="currentColor" strokeWidth="2.6"
        strokeLinecap="round" strokeLinejoin="round" />
  <path d="M20 8 L27 16 L20 24" stroke="currentColor" strokeWidth="2.6"
        strokeLinecap="round" strokeLinejoin="round" />
  {/* AI spark */}
  <path d="M16 10 L17.5 14.5 L22 16 L17.5 17.5 L16 22 L14.5 17.5 L10 16 L14.5 14.5 Z"
        fill="var(--accent)" />
</svg>
```

### 6.2 Favicon & `index.html`

- `<html lang="fr">`, `<meta charset="UTF-8">`, viewport standard, `<div id="root">` + `<script type="module" src="/src/main.tsx">`.
- Titre : **`Autospec — usine à features BMAD`**.
- Favicon : même dessin en SVG data-URI, mais avec des couleurs figées (chevrons `#4f8cff`, spark `#3ecf8e` — inversé par rapport au logo in-app) :

```html
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Cpath d='M12 8 L5 16 L12 24' fill='none' stroke='%234f8cff' stroke-width='2.6' stroke-linecap='round' stroke-linejoin='round'/%3E%3Cpath d='M20 8 L27 16 L20 24' fill='none' stroke='%234f8cff' stroke-width='2.6' stroke-linecap='round' stroke-linejoin='round'/%3E%3Cpath d='M16 10 L17.5 14.5 L22 16 L17.5 17.5 L16 22 L14.5 17.5 L10 16 L14.5 14.5 Z' fill='%233ecf8e'/%3E%3C/svg%3E" />
```

---

*Couverture : intégralité de `frontend/src/index.css` — **3533 lignes CSS** (tokens dark/light, resets, 6 @keyframes, 6 media queries dont 3 `prefers-reduced-motion`, et l'ensemble des classes réparties en ~30 groupes de composants).*
