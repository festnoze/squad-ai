# Référence UI Autospec — documentation de recréation

Documentation exhaustive du frontend **actuel** d'Autospec, rédigée comme base de travail
pour la refonte UI : tout ce qu'il faut pour recréer l'interface à l'identique
(design system, layout, état, composants, interactions, libellés).

> Snapshot du code au 2026-07-02 (branche `main`). Sources : `frontend/src/` —
> ~10 000 lignes hors tests (dont `index.css` 3533 lignes, `Board.tsx` 1816 lignes).

## Stack

| Élément | Valeur |
|---|---|
| Framework | React 18.2 + TypeScript 5.4, Vite 5 (port **5183**, proxy → backend FastAPI **8100**) |
| Styles | CSS pur dans un seul fichier `src/index.css`, variables sous `:root[data-theme]` (dark défaut / light) |
| État | Aucun routeur, aucun store externe — tout dans `App.tsx` (useState/useRef), temps réel via **SSE** (`/api/stream`) |
| i18n | Maison, stores module-level (pas de Context), langues **en/fr**, persistance `localStorage` (`autospec.lang`, `autospec.theme`) |
| Tests | Vitest + Testing Library (unit), Playwright (e2e) |

## Les documents

| Fichier | Contenu |
|---|---|
| [01-design-system.md](01-design-system.md) | Tokens CSS (palette dark/light exacte), thème, typo, 6 `@keyframes`, catalogue des ~280 classes par zone, media queries, logo/favicon SVG verbatim |
| [02-shell-etat-donnees.md](02-shell-etat-donnees.md) | `main.tsx`, config Vite, `App.tsx` (état complet, effets, SSE, layout JSX, props passées aux enfants), diagrammes layout + machine à états des écrans, **48 endpoints** `api.ts`, tous les types de `types.ts`, logique dérivée `work.ts`, mécanisme i18n/thème |
| [03-composants-majeurs.md](03-composants-majeurs.md) | **Board** (navigation epics → epic → US → task, 22 unités internes : cartes, badges, critères, éditeur de story, diff viewer, drag-&-drop priorités), **Activity** (flux d'événements, chips-filtres par statut, chat d'item, région « À traiter »), **RunPanel** (phases, bannières, coûts, logs), **LlmActivity** (cartes d'interactions LLM, polling 3 s), **ProjectBar** (chips projets, actions) |
| [04-composants-secondaires.md](04-composants-secondaires.md) | WorkspaceViews (onglets à gating), IterationsView, ChatPanel, DepGraphPanel (SVG topologique, chemin critique), CodeViewer, Stepper (8 étapes, staleness 25 s), ComponentsPanel, SettingsModal, ProjectSetup, Dashboard, PlanReviewPanel, LanguagePanel, BacklogPanel, ArchitecturePanel, CollapsibleSection |

## Vue d'ensemble du layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ <header>  [Logo] Autospec        [🤖 provider·modèle ▾]  [📊] [⚙️]  │
├──────────────────────────────────────────────────────────────────────┤
│ <ProjectBar>  [chip P1][chip P2*]…  [👁 archivés] [＋ nouveau]        │
├──────────────────────────────────────────────────────────────────────┤
│ (.error-banner / .toasts — conditionnels)                            │
├──────────────────────────────────────────────────────────────────────┤
│ <main class="workspace">   (ou class="home" si aucun projet)         │
│ ┌───────────────────┐  ┌────────────────────────────────────────┐   │
│ │ .col-left (rail   │  │ .col-right (scène)                     │   │
│ │  380px)           │  │  WorkspaceViews (Board/Graphe/Itér.)   │   │
│ │  ChatPanel        │  │  RunPanel                              │   │
│ │  ComponentsPanel  │  │  CodeViewer                            │   │
│ │  LanguagePanel    │  └────────────────────────────────────────┘   │
│ │  BacklogPanel     │                                               │
│ │  ArchitecturePanel│   Modales : ProjectSetup / Dashboard /        │
│ │  PlanReviewPanel  │   SettingsModal (backdrop superposé)          │
│ └───────────────────┘                                               │
└──────────────────────────────────────────────────────────────────────┘
  Responsive : < 1200 px → body[data-density="compact"]
```

Écrans (pas de routeur) : **HOME** (0 projet, modale Setup forcée) ⇄ **WORKSPACE**
(projet sélectionné) ; 3 modales superposables. Détail : [02 §3.2](02-shell-etat-donnees.md).

## Invariants à préserver (ou remettre en cause explicitement) dans la refonte

- **Un seul canal d'« attention »** : token `--attention` + une seule pulsation, réservés à failed/blocked/needs-attention (P13/P15, colorblind-safe).
- **Temps réel** : SSE (`state`/`log`/`deleted`/`notify`/`tick`) avec heartbeats `tick` stockés à part pour ne jamais écraser le state riche ; fusion optimiste des `guidance`.
- **Gating d'onglets** dans WorkspaceViews (Activité par défaut en `build`, Itérations dès 2 itérations, Graphe si tasks/deps).
- **Densité adaptative** pilotée par tokens (`--rail-w`, `--font-sm`, `--row-pad`) et `body[data-density]`.
- **i18n en/fr complet** : chaque libellé passe par `messages["ns.clé"]` (21 namespaces).
- `prefers-reduced-motion` respecté (3 media queries neutralisent les animations).

## Correspondance source → doc

| Source (`frontend/src/`) | Doc |
|---|---|
| `index.css`, `i18n/theme.ts`, `components/Logo.tsx`, `index.html` | 01 |
| `main.tsx`, `App.tsx`, `api.ts`, `types.ts`, `work.ts`, `i18n/i18n.ts`, `i18n/messages/*` | 02 |
| `components/{Board,Activity,RunPanel,LlmActivity,ProjectBar}.tsx` | 03 |
| `components/{WorkspaceViews,IterationsView,ChatPanel,DepGraphPanel,CodeViewer,Stepper,ComponentsPanel,SettingsModal,ProjectSetup,Dashboard,PlanReviewPanel,LanguagePanel,BacklogPanel,ArchitecturePanel,CollapsibleSection}.tsx` | 04 |

Tous les fichiers source non-test de `frontend/src/` sont couverts.

## Lancer l'UI actuelle

```bash
cd frontend && npm install && npm run dev   # Vite sur http://localhost:5183
# backend attendu sur :8100 (proxy /api configuré dans vite.config.ts)
```

Voir aussi les documents de refonte : [../01-analysis-and-proposals.md](../01-analysis-and-proposals.md)
et [../02-ux-architecture.md](../02-ux-architecture.md).
