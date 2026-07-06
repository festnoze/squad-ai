# Autospec UI/UX — Améliorations post-MVP (quick wins & roadmap)

> Suite de [01-analysis-and-proposals.md](01-analysis-and-proposals.md) et
> [02-ux-architecture.md](02-ux-architecture.md). Périmètre : **Phase 1** = polish à
> fort impact (identifiants `Q#`), livrée sur cette branche ; **Phase 2** = roadmap
> différée (identifiants `R#`). Frontend-first : **aucun changement backend pour les
> Q#** — une seule correction backend (bug préexistant de suppression de workspace,
> voir §6) découverte par la fiabilisation de la suite e2e.

## 0. Contexte & méthode

Le MVP de la refonte (02) est livré : stage tracker (`Stepper`), vue **Activité**
canonique (heartbeat `tick`, grey-out de fraîcheur, bannière d'approbation, chat ciblé
par item), shell adaptatif piloté par tokens, thèmes sombre/clair. Ce document part
d'un **audit du code** de `frontend/src` (post-MVP) et recense la dette UX résiduelle,
puis la traite en deux phases.

Critères de sélection (hérités de 02) :

- **Frontend-first** : un item n'entre en Phase 1 que s'il est réalisable avec les
  API existantes.
- **Additif** : la suite e2e Playwright exhaustive (`e2e/autospec.spec.ts`,
  `e2e/improve-ux.spec.ts`) et les tests vitest restent verts ; toute rupture
  volontaire (Q2) est corrigée dans le même commit.
- **Invariants du design system** : canal `--attention` unique (le seul pulse est
  réservé à failed/blocked/needs-attention), `prefers-reduced-motion` respecté,
  CSS dans `index.css` avec les tokens existants, i18n en/fr complet, **aucune
  dépendance nouvelle** en Phase 1.

## 1. Constats résiduels (audit vérifié dans le code)

| # | Constat | Ancrage |
| --- | --- | --- |
| C1 | 4 `window.confirm()` natifs (suppression projet, rollback, restart from scratch, suppression story) | `App.tsx:327,442,451`, `Board.tsx:805` |
| C2 | **Aucun** gestionnaire `Escape` sur les 9 overlays (modales Setup/Dashboard/Settings, CodeViewer, 2 overlays de diff, 3 popovers) | grep `Escape` = 0 résultat |
| C3 | Anneaux de focus quasi absents : 3 règles `:focus-visible` locales, pas de règle globale | `index.css` |
| C4 | Logs non filtrables (mur de texte, cap 800 lignes) alors que chaque ligne porte un tag `source` (`dev:US-3`, `qa:…`) | `RunPanel.tsx` |
| C5 | Aucune recherche sur le Board (100+ stories = scroll) ; seul filtre existant : stream (ST-12) | `Board.tsx` |
| C6 | Coupure SSE silencieuse : reconnexion invisible, l'utilisateur peut lire un état périmé sans le savoir | `api.ts` (`connectEvents`) |
| C7 | `last_error` présent sur stories/tâches (`types.ts`) mais jamais affiché dans Activité ; échec de fetch `LlmActivity` avalé silencieusement | `Activity.tsx`, `LlmActivity.tsx` |
| C8 | Sémantique a11y : pas de `role="log"`/`aria-live` sur les fils de messages, inputs de ProjectSetup sans label, boutons icône sans `aria-label` (title seul) | `ChatPanel.tsx`, `ProjectSetup.tsx`, `ProjectBar.tsx` |
| C9 | Pas de copier-coller assisté (code, diff, logs) | `CodeViewer.tsx`, panneaux diff |
| C10 | Piège e2e préexistant : les specs assertent des libellés **français** alors que `DEFAULT_LANG = "en"` et qu'aucun seed localStorage n'existe côté Playwright | `i18n.ts:13`, `e2e/*` |

## 2. Phase 1 — Quick wins (Q0–Q7)

Chaque item : problème → décision → périmètre fichiers → i18n → tests.

### Q0 — Primitives partagées (fondations, zéro changement de comportement)

- **Bus de toasts module-level** (`src/toast.ts`) : `notify(level, title, body?)` +
  `subscribeToasts(fn)`, sur le modèle du store `i18n.ts`. `App.tsx` s'abonne et
  alimente son état `toasts` existant ; le chemin SSE `notify` est inchangé.
- **`ConfirmDialog`** (`src/components/ConfirmDialog.tsx`) + service
  `confirmAction(opts): Promise<boolean>` et un `<ConfirmHost/>` unique dans App.
  Réutilise `.modal-backdrop`/`.modal` et le pattern `role="dialog" aria-modal`
  de SettingsModal. Autofocus sur Annuler (défaut sûr), `Escape` = annuler,
  `Enter` = confirmer, `data-testid="confirm-accept"`. Couleurs danger statiques,
  **pas de pulse**.
- **`useEscapeToClose(active, onClose)`** (`src/hooks.ts`) : écoute `keydown` quand
  actif ; respecte `e.defaultPrevented` et appelle `preventDefault()` — les overlays
  empilés se ferment du plus interne au plus externe.
- **`copyText(text, t)`** (`src/clipboard.ts`) : `navigator.clipboard` + repli
  `execCommand("copy")`, feedback via le bus de toasts.
- **CSS** (`index.css`) : `.confirm-dialog`, `.input-hint`, `.log-search` et une
  **règle de focus globale** `button/input/textarea/select:focus-visible
  { outline: 2px solid var(--accent); outline-offset: 2px; }`.
- i18n : réutilise `common.cancel/confirm/delete` ; ajoute `common.copy/copied/copyFailed`.
- Tests : `ConfirmDialog.test.tsx`, `toast.test.ts`, `clipboard.test.ts`.

### Q1 — Clavier & focus (C2, C3, C8 partiel)

- `useEscapeToClose` branché sur : App (modale Setup, popover provider), Dashboard,
  SettingsModal, CodeViewer, Activité (overlay diff + menu ⋯), Board (overlay diff de
  StoryDetail), RunPanel (menu livraison).
- `aria-label` sur les boutons icône (chips ProjectBar ⏹ ▶ 📦 ↩ ✕, ✕ de la bannière
  reprise RunPanel) — **même chaîne que le `title` existant** pour ne pas casser les
  sélecteurs `getByTitle` des e2e.
- Indices d'envoi (`.input-hint`) sous l'input du ChatPanel (« Entrée pour envoyer… »)
  et sous l'ItemChat d'Activité (« Ctrl+Entrée… »).
- Raccourcis globaux de changement de vue : **différés en R2** (leur place est dans la
  palette Cmd-K ; un raccourci global exige un garde-focus et une surface de
  découverte — surface de régression réelle pour une valeur faible isolément).

### Q2 — ConfirmDialog de marque (C1) ⚠ atomique avec l'édition e2e

- Les 4 sites passent à `await confirmAction({...})` ; les clés de corps existantes
  (`app.confirmDelete/confirmRollback/confirmRestartScratch`,
  `board.confirmDeleteStory`) sont réutilisées ; ajout des clés de titre.
- **Même commit** : la boucle de nettoyage d'`autospec.spec.ts` (auto-accept des
  dialogs natifs) est remplacée par un clic sur `confirm-accept` ; audit des deux
  specs pour tout flux destructif. Les handlers `page.on("dialog")` restent
  (inoffensifs).

### Q3 — Filtres de logs RunPanel (C4, frontend-only)

- Dans la barre de logs : recherche texte, `<select>` des `source` distinctes,
  bascule « erreurs seulement » (heuristique ❌/⚠️ — le backend n'émet **pas** de
  niveau ; un vrai champ `level` est noté comme suivi backend optionnel, non requis),
  compteur `{shown}/{total}`. Filtrage client sur le buffer ≤ 800 lignes.
  Auto-scroll uniquement quand aucun filtre n'est actif.

### Q4 — Recherche Board (C5)

- Input dans `.board-top` (niveaux `epics`/`epic`), match insensible aux diacritiques
  (normalisation NFD) sur id/titre/description de story + titre d'épic ; se compose
  avec le filtre stream existant. Niveau épics : seules les cartes ayant ≥ 1 story
  qui matche (ou dont le titre matche) restent visibles — les barres de progression
  restent calculées sur les listes non filtrées. Placeholder « aucun résultat » avec
  écho de la requête.

### Q5 — États d'erreur & de connexion manquants (C6, C7)

1. **« Reconnexion… »** : paramètre additif `onStatus?: (connected) => void` sur
   `connectEvents` (`es.onopen`/`es.onerror`) ; pastille **ambre statique** dans le
   header (pas de pulse — canal `--attention` réservé).
2. **CTA d'erreur sur ligne échouée (Activité)** : si `status === "failed"` et
   `last_error` présent, bouton « ⚠ Voir l'erreur » qui ouvre le tiroir avec un
   `<pre class="activity-last-error">` (tronqué ~2000 caractères).
3. **Échec de premier chargement LlmActivity** : note « Historique indisponible » au
   lieu d'un vide trompeur — sauf 404 (pas d'historique encore : cas normal) ; le
   polling suivant reste silencieux.

### Q6 — Sémantique a11y (C8)

- `role="log" aria-live="polite"` sur `.chat-messages` (ChatPanel) et sur la liste de
  guidance de l'ItemChat (Activité) ; `aria-label` sur le textarea du chat.
- `aria-label` sur les inputs nom/objectif/brief de ProjectSetup (le pattern existe
  déjà pour brownfield/budget).
- **Rejeté sciemment** : des titres `h4` par ligne d'Activité (pollution du plan de
  document pour 100+ lignes ; les lignes sont des items de liste, pas des sections).

### Q7 — Copier dans le presse-papiers (C9)

- Boutons : en-tête CodeViewer (contenu du fichier, désactivé pendant le chargement),
  panneaux diff d'Activité et du Board (copie du diff), barre de logs RunPanel (copie
  des lignes **actuellement filtrées**).
- **Rejeté** : un bouton copier par ligne de log (coût DOM × 800 ; la virtualisation
  est en R1).

## 3. Décisions transverses

- Un seul **bus de toasts** module-level (pattern maison `i18n.ts`) — pas de Context,
  utilisable hors composants ; App reste l'unique rendu des toasts.
- Un seul **service de confirmation** (`confirmAction`) — toute action destructive
  future (y compris la palette R2) passe par lui.
- Un seul **hook Escape** — comportement d'empilement défini une fois
  (`defaultPrevented`).
- **Focus ring global** plutôt que règle par règle — les 3 règles locales existantes
  restent (compatibles).
- Les invariants de 02 tiennent : canal `--attention` unique, pas de nouveau pulse,
  `prefers-reduced-motion` inchangé (aucune nouvelle animation en Phase 1), i18n
  en/fr pour chaque libellé.

## 4. Phase 2 — Roadmap (R1–R6)

| # | Item | Approche & dépendances | Taille |
| --- | --- | --- | --- |
| R1 | **Virtualisation (P17)** | Rendu fenêtré des lignes Activité / listes Board / logs. Soit `react-window` (nouvelle dépendance, à approuver), soit un windower manuel (~80 lignes) sur hauteurs de ligne fixes (les tokens `--row-pad` les rendent prévisibles). À faire **avant** R3. | M |
| R2 | **Palette Cmd-K (P14)** | Registre de commandes (retry/force/diff/chat/goto) avec chip de cible obligatoire, fuzzy-match sur stories/tâches/épics ; les verbes destructifs passent par `confirmAction` (Q0/Q2). Absorbe les raccourcis de vue différés de Q1. | L |
| R3 | **Consolidation des vues** | Activité par défaut dans **toutes** les phases (le gating actuel = `build`), Board rétrogradé en lentille d'exploration accessible depuis les lignes ; réécriture e2e conséquente (les specs naviguent lourdement le Board). | M + M (e2e) |
| R4 | **Extraction design system (P15)** | Extraire `Badge`, `Card`, `Drawer`, `Toolbar`, `Menu` de la soupe de classes CSS ; mécanique mais large (Board.tsx ~1850 lignes est le premier payeur) ; après R3 pour cibler les surfaces survivantes. | L |
| R5 | **Responsive/mobile** | Barre d'onglets basse < 1100px, Stepper vertical < 768px ; s'appuie sur les tokens `--rail-w`/`data-density` existants ; surtout `index.css` + un composant nav + un project Playwright viewport. | M |
| R6 | **Undo/soft-delete des stories** | **Seul item nécessitant du backend** (additif : tombstone `deleted_at` + endpoint restore + exclusion scheduler) ; côté frontend, toast avec action « Annuler » (petite extension du bus Q0). | M back + S front |

## 5. Hors périmètre / rejeté

- **Raccourcis clavier globaux** de changement de vue → R2 (palette).
- **Champ `level` sur les logs backend** → l'heuristique Q3 suffit ; noté comme
  suivi additif optionnel.
- **Bouton copier par ligne de log** → coût DOM ; couvert par « copier les lignes
  filtrées » (Q7) puis R1.
- **Thème clair retravaillé, timeline scrubber, heatmap, autonomy dial…** → déjà
  tranchés DROP dans 02 §2 ; inchangés.

## 6. Vérification

- **Unit** : `cd frontend && npm run test:unit` (vitest) — après chaque groupe de
  fichiers.
- **E2E** : `cd frontend && npm run test:e2e` (build puis Playwright contre le
  backend démo hermétique `FAKE_AGENTS=1`, port 8123). Les deux specs restent
  vertes ; `autospec.spec.ts` est modifiée **volontairement** par Q2 (dialog de
  confirmation) — même commit.
- **Corrections préexistantes livrées avec la branche** (constatées au baseline,
  indépendantes des Q#) :
  - seed `autospec.lang=fr` via `addInitScript` dans les deux specs (C10) ;
  - `.first()` sur `getByText(/Qualité du plan/)` (le libellé apparaît dans
    ArchitecturePanel **et** PlanReviewPanel — violation du strict mode) ;
  - retry sur le 409 de `DELETE /api/projects/{id}` dans les specs, qui a révélé
    un **bug backend réel** : les venvs de projet sont hardlinkés depuis le cache
    uv, donc une DLL (.pyd) du workspace partage son file-object avec le backend
    lui-même — tant qu'un processus python l'a chargée, Windows interdit sa
    suppression et le 409 « workspace verrouillé » devenait **éternel** (un
    utilisateur ne pouvait plus supprimer un projet construit). Correction dans
    `_force_delete_workspace` (`api/server.py`) : les fichiers indélébiles sont
    **déplacés** (renommage permis sur une DLL chargée) vers une corbeille
    `.autospec-trash` hors du workspace, purgée en best-effort à chaque passage ;
    `e2e/global-setup.ts` tolère une corbeille encore verrouillée au wipe.
- **Backend** : intouché en Phase 1 → `pytest` en simple contrôle de non-régression.
- **Manuel** (backend :8100 + `npm run dev` → http://localhost:5183) : parcours Tab
  (anneaux visibles), Escape sur chaque overlay, suppression d'un projet (dialog de
  marque), kill du backend (pastille « Reconnexion… » apparaît puis disparaît),
  filtrage des logs pendant un build démo, recherche board, copie depuis CodeViewer
  (toast), re-vérification de chaque nouveau libellé en EN et FR, thème clair +
  émulation `prefers-reduced-motion`.
