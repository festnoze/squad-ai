# 02 — Shell applicatif, état global et couche données (frontend Autospec)

Référence exhaustive pour recréer à l'identique le shell React 18 + Vite + TypeScript du frontend Autospec.
Fichiers sources couverts : `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/api.ts`,
`frontend/src/types.ts`, `frontend/src/work.ts`, `frontend/src/i18n/*`, `frontend/vite.config.ts`, `frontend/index.html`.

---

## 1. Bootstrap

### 1.1 `index.html`

- `<html lang="fr">`, `<meta charset="UTF-8">`, viewport standard.
- Favicon SVG **inline** (data-URI) : deux chevrons `< >` bleus (`#4f8cff`, stroke 2.6, linecap/linejoin round) encadrant une étoile à 4 branches verte (`#3ecf8e`), viewBox `0 0 32 32`.
- `<title>Autospec — usine à features BMAD</title>`.
- Corps : `<div id="root"></div>` + `<script type="module" src="/src/main.tsx">`.

### 1.2 `src/main.tsx`

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import { initLang } from "./i18n/i18n";
import { initTheme } from "./i18n/theme";

// Applique thème + langue persistés sur <html> AVANT le premier paint.
initTheme();   // pose data-theme="dark|light" sur <html>
initLang();    // pose lang="en|fr" sur <html>

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

Points clés : un seul fichier CSS global `index.css` ; rendu sous `React.StrictMode` ; pas de router (pas de react-router — l'app est mono-page, la « navigation » est pilotée par du state local dans `App.tsx`).

### 1.3 `vite.config.ts`

| Élément | Valeur |
|---|---|
| Plugin | `@vitejs/plugin-react` |
| Port dev | **5183** |
| Cible proxy | `http://127.0.0.1:${VITE_BACKEND_PORT ?? "8100"}` (backend FastAPI) |
| Routes proxifiées | `/api/stream` (SSE, déclarée **en premier** car plus spécifique) puis `/api` (générique) |
| Agent HTTP | `http.Agent` keep-alive partagé (`keepAlive: true`, `keepAliveMsecs: 1000`, `maxSockets: 64`) |
| Timeout proxy `/api` | `PROXY_TIMEOUT_MS = 12_000` ms (backstop anti-socket bloquée) |
| Timeout proxy `/api/stream` | **aucun** (un flux SSE inactif entre deux events ne doit pas être coupé) |

Deux fabriques de proxy sur mesure :

- **`retryingProxy(target)`** (route `/api`) : remplace (via `setImmediate`, après que Vite ait posé son propre handler) le handler `error` du proxy par une version avec retry. Constantes : `CONNECT_PHASE_CODES = {ETIMEDOUT, ECONNREFUSED, EHOSTUNREACH, ENETUNREACH}` (échec avant délivrance → retry pour **toute** méthode y compris POST), `MIDSTREAM_CODES = {ECONNRESET, EPIPE}` (retry **uniquement** pour `IDEMPOTENT_METHODS = {GET, HEAD, OPTIONS}`), `MAX_RETRIES = 3`, `RETRY_DELAY_MS = 150`. Compte les tentatives par requête via `WeakMap`. À épuisement : log console `[vite] api proxy error: …` + réponse `502 text/plain "proxy error: <code>"` (ou `res.destroy()` pour un socket brut).
- **`streamProxy(target)`** (route `/api/stream`) : pas de retry ni timeout ; en cas d'erreur, `res.destroy()` silencieux (EventSource se reconnecte nativement, le backend rejoue via `Last-Event-ID`).

Config de test (Vitest) intégrée : `environment: "jsdom"`, `globals: true`, `setupFiles: ["./src/test/setup.ts"]`, `include: ["src/**/*.test.{ts,tsx}"]`, `exclude: ["e2e/**", "node_modules/**", "dist/**"]`.

---

## 2. `App.tsx` en détail (762 lignes)

Composant unique par défaut `export default function App()`. Utilise `useI18n()` pour `t`.

### 2.1 Types et helpers locaux au module

- **`interface StampedLog`** : `{ projectId: string; source: string; line: string }` — une ligne de log estampillée projet.
- **`interface NotifyToast`** : `{ id: number; level: string; title: string; body: string }`.
- **`mergeGuidance(incoming?: GuidanceEntry[], prev?: GuidanceEntry[]): GuidanceEntry[] | undefined`** : fusion par `id` ; les entrées du serveur gagnent pour les ids connus, les entrées **optimistes locales** non encore renvoyées par le serveur sont préservées (évite qu'un event `state` complet écrase une directive de chat tout juste postée).
- **`mergeStateGuidance(state: ProjectState, prev?: ProjectState): ProjectState`** : applique `mergeGuidance` sur les `guidance` de chaque story ET de chaque task de l'état entrant, en s'appuyant sur des `Map` par id des stories/tasks précédentes.

### 2.2 État complet (useState / useRef / useMemo)

| Hook | Nom | Type | Rôle |
|---|---|---|---|
| `useState` | `projects` | `ProjectState[]` | Liste complète des projets (source de vérité UI). |
| `useState` | `selectedId` | `string \| null` | Id du projet sélectionné (`null` = accueil). |
| `useState` | `showSetup` | `boolean` | Modale de création de projet ouverte. |
| `useState` | `showDashboard` | `boolean` | Modale Dashboard (métriques usine) ouverte. |
| `useState` | `showSettings` | `boolean` | Modale Paramètres ouverte. |
| `useState` | `showArchived` | `boolean` | Affiche aussi les projets archivés dans la barre. |
| `useState` | `logs` | `StampedLog[]` | Buffer global de logs (borné : `prev.slice(-800)` + 1 à chaque event `log`). |
| `useState` | `ticks` | `Record<string, ProjectTicks>` | Dernier heartbeat par projet ; ne remplace JAMAIS le state riche, ne fait que rafraîchir stage/persona/recovery item par item entre deux snapshots `state`. |
| `useState` | `busy` | `boolean` | Création de projet en cours (désactive le formulaire). |
| `useState` | `error` | `string` | Message du bandeau d'erreur global (`""` = masqué). |
| `useState` | `toasts` | `NotifyToast[]` | Toasts in-app (max 5 : `prev.slice(-4)` + nouveau ; auto-dismiss 6000 ms). |
| `useRef` | `toastIdRef` | `number` | Compteur incrémental d'ids de toasts. |
| `useState` | `provider` (setter `setProviderInfo`) | `ProviderInfo \| null` | Provider/modèle d'agents courant (`null` = backend injoignable → sélecteur masqué). |
| `useState` | `providerMenuOpen` | `boolean` | Popover provider/modèle ouvert. |
| `useState` | `discovered` | `Record<string, { models: string[]; source: "live" \| "static" }>` | Modèles découverts en live par provider (fallback : liste statique `provider.models`). |
| `useState` | `discovering` | `boolean` | Découverte de modèles en cours. |
| `useRef` | `providerRef` | `HTMLDivElement` | Ref du popover pour la fermeture au clic extérieur. |
| `useRef` | `deletedIds` | `Set<string>` | Ids des projets supprimés — empêche un event `state`/`tick` retardé de « ressusciter » un projet supprimé. |
| `useMemo` | `project` | `ProjectState \| null` | `projects.find(p => p.id === selectedId) ?? null`. |
| `useMemo` | `visibleProjects` | `ProjectState[]` | `showArchived ? projects : projects.filter(p => !p.archived)`. |
| `useMemo` | `projectLogs` | `StampedLog[]` | `logs.filter(l => l.projectId === selectedId)`. |
| (dérivé) | `canCloseSetup` | `boolean` | `visibleProjects.length > 0` — la modale de création est fermable seulement s'il reste un projet à afficher. |

Constante locale : `ACTIVE_PHASES = ["spec", "analyze", "plan", "architect", "build"]` — phases où des agents travaillent activement.

Fonction utilitaire : `upsert(state: ProjectState)` — insère en tête si inconnu, sinon remplace à l'index avec `mergeStateGuidance(state, prev[i])`.

`pushToast(level, title, body = "")` : incrémente `toastIdRef`, empile (fenêtre glissante de 5), programme la suppression à 6 s.

`guard(fn: () => Promise<void>) => () => fn().catch(e => setError(errorMessage(e)))` : enveloppe toute action API pour router l'erreur vers le bandeau.

### 2.3 Effets (useEffect)

| # | Dépendances | Rôle |
|---|---|---|
| 1 | `[providerMenuOpen, provider?.provider]` | À l'ouverture du popover (et si provider ≠ `"fake"`), lance `refreshModels(provider.provider)` (découverte live). |
| 2 | `[providerMenuOpen]` | Listener `mousedown` sur `document` : clic hors de `providerRef` → ferme le popover. Nettoyage au démontage. |
| 3 | `[]` (densité, P3) | `document.body.dataset.density = window.innerWidth < 1200 ? "compact" : "comfortable"` ; appliqué au montage + sur `resize` (le CSS porte les deltas de tokens). |
| 4 | `[]` (bootstrap) | `listProjects()` → `setProjects` ; sélectionne le premier projet **non archivé**, sinon `setShowSetup(true)` (accueil intelligent). En échec (backend down) : `setError(errorMessage(e))` + `setShowSetup(true)`. Puis `getProvider()` → `setProviderInfo` (catch → `null`). Puis demande unique de permission `Notification` navigateur si `permission === "default"` (best-effort). |
| 5 | `[]` (SSE) | `connectEvents(onEvent, onReconnect)` — voir §2.5. La fonction de désinscription retournée sert de cleanup. |
| 6 | `[visibleProjects, selectedId]` | Garde de sélection : si le projet sélectionné n'est plus visible (archivé/supprimé), repli sur `visibleProjects[0]?.id ?? null` ; si `null`, `setShowSetup(true)`. |

### 2.4 Handlers (logique métier)

- **`refreshModels(name)`** : `discoverModels(name)` → alimente `discovered[name]` ; échec silencieux (fallback statique) ; gère `discovering`.
- **`handleCreate(goal, name, autoSpec, budgetUsd, brief?, brownfieldPath?)`** : `setBusy(true)`, `createProject(...)`, `upsert(state)`, sélection du projet créé, fermeture de la modale ; erreurs → `setError` ; `finally setBusy(false)`.
- **`handleDelete(target)`** : **`window.confirm(t("app.confirmDelete", { name }))`** puis `deleteProject` ; ajoute l'id à `deletedIds`, purge `projects` et `logs` du projet (la garde de sélection choisit le suivant).
- **`handleArchive(target)` / `handleUnarchive(target)`** : appels API simples ; l'état revient par SSE.
- **`handlePlay(target)`** (chip ▶, U1) : `target.paused ? resumeProject : resumeBuild`.
- **`handleStop(target)`** (chip ⏹) : `stopProject`.
- **`switchTo(id)`** : changement de projet sélectionné. Si on **quitte** un projet dont `phase ∈ ACTIVE_PHASES` ou `running`, envoie `interruptProject(selectedId)` en fire-and-forget (tue l'appel CLI agent en vol + l'app générée pour arrêter la dépense) ; idempotent, échec ignoré.
- **`handleProviderChange(name)`** : `setProvider(name)` → met à jour `provider.provider` et `provider.model`.
- **`handleModelChange(model)`** : `setProvider(provider.provider, model)`.
- **`handleRollbackTo(n)`** : `window.confirm(t("app.confirmRollback", { n }))` → `rollbackProject(project.id, n)` (via `guard`) → toast succès (`app.rollbackToastTitle/Body`).
- **`handleRestartFromScratch()`** : destructif (efface code + epics + stories, garde le brief) → `window.confirm(t("app.confirmRestartScratch", { name }))` → `restartFromScratch` → toast (`app.restartToastTitle/Body`).

### 2.5 Gestion SSE (event handling)

Effet #5, câblé sur `connectEvents` (voir §4.3). Dispatch par `event.type` :

| Type | Traitement |
|---|---|
| `"state"` | Ignoré si `deletedIds.current.has(event.state.id)` ; sinon `upsert(event.state)` (avec fusion guidance). |
| `"deleted"` | Ajoute à `deletedIds`, retire de `projects`. |
| `"log"` | Empile `{projectId, source, line}` dans `logs` (fenêtre 800). |
| `"tick"` | Ignoré si projet supprimé ; sinon `setTicks` : stocke `{ ts, items: Object.fromEntries(items.map(it => [it.id, it])), counts, stallReason: stall_reason }` pour ce projet. Ne touche jamais au state complet. |
| `"notify"` | Crée un toast (fenêtre 5, auto-dismiss 6 s) **et**, si `Notification.permission === "granted"`, une notification navigateur `new Notification(title, { body })` (try/catch — fallback toast seul). |

Callback `onReconnect` (appelé uniquement aux RE-connexions) : re-`listProjects()` et upsert de chaque projet non supprimé (les events manqués pendant la coupure seraient sinon perdus si le ring buffer serveur a évincé) + re-`getProvider()` (pour faire réapparaître le sélecteur si le backend était down au montage).

### 2.6 Gestion des erreurs

- Toute erreur API passe par `errorMessage(e)` (api.ts) et atterrit dans le **bandeau d'erreur** global `error` (div `.error-banner`, style inline flex avec bouton ✕ `setError("")`).
- Les actions ponctuelles positives passent par des **toasts** (`pushToast`) — plus de `window.alert`/`prompt` natifs (UI8) ; seuls subsistent trois `window.confirm` (suppression, rollback, restart from scratch).
- Événement SSE illisible (JSON invalide) : ignoré avec `console.warn`.

### 2.7 Raccourcis clavier

**Aucun** raccourci clavier global dans App.tsx (pas de listener `keydown`). Accessibilité : `aria-haspopup`/`aria-expanded` sur le trigger provider, `aria-label` sur tous les boutons icônes, `aria-live="polite"` sur le conteneur de toasts, `role="menu"` sur le popover provider.

### 2.8 Structure JSX de haut niveau (layout rendu)

```
<div className="app">
  <header>
    <h1><Logo /> Autospec <span className="subtitle">{t("app.subtitle")}</span></h1>
    {provider && (
      <div className="provider-control" ref={providerRef}>
        <button className="provider-trigger" aria-haspopup="menu" ...>
          🤖 {provider|"démo"} <span className="provider-trigger-model"> · {model}</span>
          <span className="provider-caret">▾</span>            // si provider ≠ "fake"
        </button>
        {providerMenuOpen && provider !== "fake" && (
          <div className="provider-menu" role="menu">
            <label className="provider-field"> Provider <select>…available…</select> </label>
            <label className="provider-field">
              Modèle (+ hint "live"/"suggérés" : <em className="provider-hint[-live]">)
              <button className="provider-refresh">🔄</button>
              <select>…modèle courant en tête si absent de la liste, puis modelList…</select>
            </label>
          </div>
        )}
      </div>
    )}
    <button className="dash-btn" onClick={() => setShowDashboard(true)}>📊</button>
    <button className="dash-btn settings-btn" onClick={() => setShowSettings(true)}>⚙️</button>
  </header>

  {(visibleProjects.length > 0 || projects.some(p => p.archived)) && <ProjectBar …/>}

  {error && <div className="error-banner"><span>{error}</span><button>✕</button></div>}

  {toasts.length > 0 && (
    <div className="toasts" aria-live="polite">
      {toasts.map(t => (
        <div className={`toast toast-${t.level}`}>
          <div className="toast-text"><div className="toast-title"/><div className="toast-body"/></div>
          <button className="toast-close">✕</button>
        </div>))}
    </div>
  )}

  {showDashboard && <Dashboard onClose={…} />}
  {showSettings && <SettingsModal onClose={…} />}
  {showSetup && (
    <div className="modal-backdrop" onClick={() => canCloseSetup && setShowSetup(false)}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        {canCloseSetup && <button className="modal-close">✕</button>}
        <ProjectSetup onCreate={handleCreate} busy={busy} />
      </div>
    </div>
  )}

  {!project ? (
    <main className="home">
      {!showSetup && <div className="placeholder">{t("app.placeholder")}</div>}
    </main>
  ) : (
    <main className="workspace">
      <div className="col-left">
        <ChatPanel … /> <ComponentsPanel … /> <LanguagePanel … />
        <BacklogPanel … /> <ArchitecturePanel … /> <PlanReviewPanel … />
      </div>
      <div className="col-right">
        <WorkspaceViews … /> <RunPanel … /> <CodeViewer … />
      </div>
    </main>
  )}
</div>
```

### 2.9 Composition des enfants et props exactes

Note transverse : les props sont systématiquement défensives (`?? []`, `?? ""`, `?? -1`, `?? false`) pour tolérer d'anciens états persistés sans certains champs.

| Composant (import) | Props passées |
|---|---|
| `Logo` (`./components/Logo`) | — |
| `ProjectBar` | `projects` (tous, y compris archivés), `selectedId` (`showSetup ? null : selectedId`), `onSelect(id)` → `switchTo(id)` + `setShowSetup(false)`, `onNew` → `setShowSetup(true)`, `onDelete=handleDelete`, `showArchived`, `onToggleArchived` (toggle), `onArchive`, `onUnarchive`, `onPlay=handlePlay`, `onStop=handleStop`. |
| `Dashboard` | `onClose` → `setShowDashboard(false)`. |
| `SettingsModal` | `onClose` → `setShowSettings(false)`. |
| `ProjectSetup` | `onCreate=handleCreate`, `busy`. |
| `ChatPanel` | `chat={project.chat ?? []}`, `phase={project.phase}`, `onSend={(m) => guard(() => sendChat(project.id, m))()}`, `specMode={project.spec_mode ?? "interview"}`, `onSetSpecMode={(m) => guard(() => setSpecMode(project.id, m))()}`, `awaitingBrainstorm={project.awaiting_brainstorm_decision ?? false}`, `brainstormTechniques={project.brainstorm_techniques ?? []}`, `onResolveBrainstorm={(accept) => guard(() => resolveBrainstorm(project.id, accept))()}`. |
| `ComponentsPanel` | `components={project.components ?? []}`, `onUpdate={(components: ProductComponent[]) => guard(() => updateComponents(project.id, components))()}`, `onSetup={guard(() => setupComponents(project.id))}`. |
| `LanguagePanel` | `language={project.backend_language}`, `complexity={project.language_complexity}`, `criticality={project.language_criticality}`, `rationale={project.language_rationale}`, `onSet={(lang) => void guard(() => setLanguage(project.id, lang).then(() => undefined))()}`. |
| `BacklogPanel` | `backlog={project.backlog ?? []}`. |
| `ArchitecturePanel` | `architecture={project.architecture ?? ""}`, `planQuality={project.plan_quality ?? -1}`. |
| `PlanReviewPanel` | `planQuality={project.plan_quality ?? -1}`, `issues={project.plan_review_issues ?? []}`, `suggestions={project.plan_review_suggestions ?? []}`. |
| `WorkspaceViews` | `epics={project.epics ?? []}`, `stories={project.stories ?? []}`, `streams={project.streams}`, `projectId={project.id}`, `phase={project.phase}`, `iterationUsage={project.iteration_usage}`, `onRollbackTo={handleRollbackTo}`, `ticks={ticks[project.id]}`, `awaitingApproval={project.awaiting_approval}`, `onApprove={guard(() => approveProject(project.id))}`, `onReject={guard(() => rejectProject(project.id))}`. |
| `RunPanel` | `project`, `logs={projectLogs}`, `onRun={(args: string) => guard(() => runProject(project.id, args))()}`, `onStop`, `onPause`, `onResume`, `onStopApp`, `onResumeBuild`, `onRetryFailed`, `onRestartFromScratch=handleRestartFromScratch`, `onDocument`, `onCancelResume`, `onApprove`, `onReject` (tous via `guard(...)` sur l'API correspondante), `onDeploy` (async : `deployProject` → toast avec `created.join(", ")` ou `deployToastNone`), `onExportZip={() => window.open(exportZipUrl(project.id), "_blank")}`, `onGitExport` (async : `gitExportProject` → toast avec `commit.slice(0, 12)`). |
| `CodeViewer` | `projectId={project.id}`. |

---

## 3. Diagrammes

### 3.1 Layout principal (zones d'écran)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ <header>                                                                     │
│  [Logo] Autospec  (subtitle)      [🤖 provider · modèle ▾]   [📊]  [⚙️]     │
├──────────────────────────────────────────────────────────────────────────────┤
│ <ProjectBar>  [chip P1][chip P2*][chip P3 ▶/⏹/archiver/✕] … [👁 archivés][＋]│
├──────────────────────────────────────────────────────────────────────────────┤
│ [.error-banner : message d'erreur global                                ✕ ] │  (conditionnel)
├──────────────────────────────────────────────────────────────────────────────┤
│ [.toasts : pile de .toast-{level} (max 5, auto-dismiss 6 s)             ]   │  (conditionnel)
├──────────────────────────────────────────────────────────────────────────────┤
│ <main class="workspace">              (ou class="home" si aucun projet)     │
│ ┌───────────────────────────┐  ┌───────────────────────────────────────────┐│
│ │ .col-left                 │  │ .col-right                                ││
│ │  ┌─────────────────────┐  │  │  ┌─────────────────────────────────────┐  ││
│ │  │ ChatPanel           │  │  │  │ WorkspaceViews                      │  ││
│ │  ├─────────────────────┤  │  │  │ (Board / graphe deps / itérations)  │  ││
│ │  │ ComponentsPanel     │  │  │  ├─────────────────────────────────────┤  ││
│ │  ├─────────────────────┤  │  │  │ RunPanel (run/stop/pause/logs/…)    │  ││
│ │  │ LanguagePanel       │  │  │  ├─────────────────────────────────────┤  ││
│ │  ├─────────────────────┤  │  │  │ CodeViewer (fichiers générés)       │  ││
│ │  │ BacklogPanel        │  │  │  └─────────────────────────────────────┘  ││
│ │  ├─────────────────────┤  │  └───────────────────────────────────────────┘│
│ │  │ ArchitecturePanel   │  │                                               │
│ │  ├─────────────────────┤  │   Modales superposées (backdrop) :            │
│ │  │ PlanReviewPanel     │  │   ProjectSetup / Dashboard / SettingsModal    │
│ │  └─────────────────────┘  │                                               │
│ └───────────────────────────┘                                               │
└──────────────────────────────────────────────────────────────────────────────┘
  Responsive : < 1200 px → body[data-density="compact"], sinon "comfortable".
```

### 3.2 Transitions d'écrans (machine à états UI)

Il n'y a pas de routeur : les « écrans » sont dérivés de `selectedId`, `showSetup`, `showDashboard`, `showSettings`.

```
                     boot (mount)
                          │
              listProjects() OK ?
              ┌───────────┴─────────────────┐
        oui, ≥1 projet visible        non (0 projet OU erreur backend)
              │                             │
              ▼                             ▼
   ┌─────────────────────┐        ┌───────────────────────┐
   │ WORKSPACE           │        │ HOME + modale SETUP   │
   │ (project ≠ null)    │        │ (placeholder si setup │
   └─────────┬───────────┘        │  fermée)              │
             │                    └──────────┬────────────┘
   onSelect(id) sur ProjectBar               │ handleCreate OK
   (switchTo : interrupt du projet           │ → upsert + select
    actif quitté) ────────────────►──────────┘ → WORKSPACE
             │
   ＋ Nouveau → showSetup=true (modale par-dessus l'écran courant ;
                fermable seulement si canCloseSetup = ≥1 projet visible)
             │
   suppression/archivage du projet sélectionné
     → garde useEffect : select visibleProjects[0] sinon null+SETUP
             │
   📊 → modale Dashboard (onClose ferme)      ⚙️ → modale SettingsModal (onClose ferme)
```

---

## 4. `api.ts` — couche d'accès HTTP + SSE

### 4.1 Base URL et helpers

- **Base URL** : chemins relatifs `/api/...` — servis par le proxy Vite en dev (cible `127.0.0.1:8100`), même origine en prod. Aucune constante de base configurable côté client.
- **`clientUuid(): string`** (exporté) : id client pour POST idempotents (`crypto.randomUUID()` si dispo, sinon fallback `"g-" + Math.random().toString(36).slice(2) + Date.now().toString(36)`).
- **`delay(ms)`** : promesse temporisée (interne).
- **`fetchIdempotent(input, init?, retries = 2)`** (interne) : `fetch` avec retry des transitoires proxy/loopback Windows — re-tente sur rejet réseau **et** sur statuts `502/503/504`, backoff `150 * (attempt + 1)` ms. À n'utiliser **que** pour des requêtes idempotentes (jamais création/append sans id de dédup).
- **`json<T>(resp)`** (interne) : si `!resp.ok`, lit le corps, extrait `detail` du JSON FastAPI (`{"detail": "..."}`) sinon garde le texte brut, et `throw new Error(\`Erreur ${resp.status} : ${detail}\`)` ; sinon `resp.json()`.
- **`errorMessage(e: unknown): string`** (exporté) : `e instanceof Error ? e.message : String(e)`.

### 4.2 Fonctions exportées (endpoints HTTP)

Toutes async sauf mention. « idem. » = passe par `fetchIdempotent`.

| Fonction | Méthode & chemin | Corps / params | Retour |
|---|---|---|---|
| `createProject(goal, name, autoSpec, budgetUsd?, brief?, brownfieldPath?, productProfile?)` | POST `/api/projects` | `{ goal, name, auto_spec, budget_usd? (si > 0), brief? (si non vide), brownfield_path? (si non vide), product_profile? (si ≠ "auto") }` | `{ id: string; state: ProjectState }` |
| `listProjects()` | GET `/api/projects` | — | `ProjectState[]` |
| `sendChat(projectId, message)` | POST `/api/projects/{id}/chat` | `{ message }` | `void` |
| `setSpecMode(projectId, mode)` | POST `/api/projects/{id}/spec-mode` | `{ mode: "interview" \| "brainstorm" }` | `void` |
| `resolveBrainstorm(projectId, accept)` | POST `/api/projects/{id}/brainstorm-decision` | `{ accept: boolean }` | `void` |
| `stopProject(projectId)` | POST `/api/projects/{id}/stop` | — | `void` |
| `interruptProject(projectId)` | POST `/api/projects/{id}/interrupt` (idem.) | — | `void` — tue l'appel CLI agent + l'app générée, pipeline → « stopped » |
| `stopApp(projectId)` | POST `/api/projects/{id}/stop-app` | — | `void` |
| `pauseProject(projectId)` | POST `/api/projects/{id}/pause` | — | `void` |
| `resumeProject(projectId)` | POST `/api/projects/{id}/resume` | — | `void` |
| `approveProject(projectId)` | POST `/api/projects/{id}/approve` | — | `void` |
| `rejectProject(projectId)` | POST `/api/projects/{id}/reject` | — | `void` |
| `getIterations(projectId)` | GET `/api/projects/{id}/iterations` | — | `number[]` (champ `iterations` de la réponse) |
| `rollbackProject(projectId, iteration)` | POST `/api/projects/{id}/rollback` | `{ iteration: number }` | `void` |
| `deployProject(projectId)` | POST `/api/projects/{id}/deploy` | — | `{ created: string[] }` |
| `deleteProject(projectId)` | DELETE `/api/projects/{id}` | — | `void` |
| `archiveProject(projectId)` | POST `/api/projects/{id}/archive` | — | `void` |
| `unarchiveProject(projectId)` | POST `/api/projects/{id}/unarchive` | — | `void` |
| `runProject(projectId, args = "")` | POST `/api/projects/{id}/run` (idem. — le backend garde contre un double lancement) | `{ args }` | `void` |
| `resumeBuild(projectId)` | POST `/api/projects/{id}/resume-build` | — | `void` |
| `retryFailed(projectId)` | POST `/api/projects/{id}/retry-failed` | — | `void` |
| `restartFromScratch(projectId)` | POST `/api/projects/{id}/restart` | — | `void` |
| `splitItem(projectId, itemId)` | POST `/api/projects/{id}/items/{itemId}/split` | — | `void` |
| `cancelResume(projectId)` | POST `/api/projects/{id}/cancel-resume` | — | `void` |
| `editStory(projectId, storyId, patch)` | PATCH `/api/projects/{id}/stories/{storyId}` | `StoryPatch` | `void` |
| `addStory(projectId, body)` | POST `/api/projects/{id}/stories` | `NewStoryBody` | `void` |
| `deleteStory(projectId, storyId)` | DELETE `/api/projects/{id}/stories/{storyId}` | — | `void` |
| `rebuildStory(projectId, storyId)` | POST `/api/projects/{id}/stories/{storyId}/rebuild` | — | `void` |
| `forceDoneStory(projectId, storyId)` | POST `/api/projects/{id}/stories/{storyId}/force-done` | — | `void` |
| `rebuildTask(projectId, taskId)` | POST `/api/projects/{id}/tasks/{taskId}/rebuild` | — | `void` |
| `forceDoneTask(projectId, taskId)` | POST `/api/projects/{id}/tasks/{taskId}/force-done` | — | `void` |
| `taskDiff(projectId, taskId)` | GET `/api/projects/{id}/tasks/{taskId}/diff` | — | `{ available: boolean; diff: string }` (via `StoryDiff`) |
| `reorderStories(projectId, priorities)` | POST `/api/projects/{id}/stories/reorder` | `{ priorities: { id: string; priority: number }[] }` | `void` |
| `listFiles(projectId)` | GET `/api/projects/{id}/files` | — | `FileListing` |
| `readFile(projectId, path)` | GET `/api/projects/{id}/files/raw?path=<encodé>` | query `path` | `FileContent` |
| `storyDiff(projectId, storyId)` | GET `/api/projects/{id}/stories/{storyId}/diff` | — | `{ available: boolean; diff: string }` |
| `getProvider()` | GET `/api/provider` (idem.) | — | `ProviderInfo` |
| `discoverModels(provider)` | GET `/api/providers/{provider}/models` (idem.) | — | `{ provider: string; models: string[]; source: "live" \| "static" }` |
| `setProvider(provider, model?)` | POST `/api/provider` (idem.) | `{ provider }` ou `{ provider, model }` | `ProviderInfo` |
| `setLanguage(projectId, language)` | PUT `/api/projects/{id}/language` (idem.) | `{ language: "python" \| "go" \| "rust" }` | `ProjectState` (champ `state` de la réponse) |
| `updateComponents(projectId, components)` | PUT `/api/projects/{id}/components` | `{ components: ProductComponent[] }` | `void` |
| `setupComponents(projectId)` | POST `/api/projects/{id}/components/setup` | — | `void` |
| `documentProject(projectId)` | POST `/api/projects/{id}/document` | — | `void` |
| `gitExportProject(projectId)` | POST `/api/projects/{id}/git-export` | — | `{ commit: string }` |
| `exportZipUrl(projectId)` (**sync**) | — (URL) | — | `string` = `` `/api/projects/${projectId}/export` `` (lien de téléchargement direct) |
| `storyChat(projectId, storyId, message, entryId?)` | POST `/api/projects/{id}/stories/{storyId}/chat` (idem. — dédup serveur sur `entry_id`) | `{ message, entry_id }` (`entry_id = entryId ?? clientUuid()`) | `{ ok: boolean; entry_id: string }` |
| `taskChat(projectId, taskId, message, entryId?)` | POST `/api/projects/{id}/tasks/{taskId}/chat` (idem.) | `{ message, entry_id }` | `{ ok: boolean; entry_id: string }` |
| `extendStory(projectId, storyId, criteria)` | POST `/api/projects/{id}/stories/{storyId}/extend` (idem. — remplacement pur ; 409 si story ≠ `todo`) | `{ acceptance_criteria: string[] }` | `ProjectState` (champ `state`) |
| `getMetrics()` | GET `/api/metrics` | — | `Metrics` |
| `getItemInteractions(projectId, itemId, limit = 20)` | GET `/api/projects/{id}/items/{itemId encodé}/interactions?limit={limit}` (idem.) | query `limit` | `AgentInteraction[]` (champ `interactions`) |

Soit **48 endpoints HTTP** + 1 URL de téléchargement + le flux SSE.

### 4.3 Mécanisme SSE — `connectEvents`

```ts
export function connectEvents(
  onEvent: (e: WsEvent) => void,
  onReconnect?: () => void,
): () => void
```

- Utilise **`EventSource`** natif sur **`/api/stream`** (SSE, en remplacement d'une ancienne WebSocket — plus résilient sur le proxy loopback Windows : reconnexion native + rejeu serveur via `Last-Event-ID`).
- État interne de fermeture : `es`, `closed`, `opened`, `reconnectTimer`.
- `onopen` : appelle `onReconnect?.()` **seulement si** `opened` était déjà true (donc jamais à la première ouverture), puis `opened = true`.
- `onmessage` : `JSON.parse(msg.data)` en `WsEvent` ; parse invalide → `console.warn` + skip.
- `onerror` : si `readyState === CONNECTING`, EventSource se reconnecte seul (backoff `retry` du serveur) — ne rien faire. Si `readyState === CLOSED` (ex. 502 transitoire, mauvais type MIME — le navigateur abandonne), fermer et relancer manuellement via `setTimeout(open, 1500)`.
- Retourne une fonction de cleanup : `closed = true`, `clearTimeout(reconnectTimer)` (évite un EventSource orphelin après démontage), `es?.close()`.
- **Types d'événements** (`WsEvent`, cf. §5) : `state`, `log`, `deleted`, `notify`, `tick` (le `tick` n'est PAS rejoué au reconnect ; il arrive ~toutes les 10 s uniquement pendant la phase BUILD).

---

## 5. `types.ts` — modèle de données complet

### 5.1 Types union / alias

| Type | Valeurs |
|---|---|
| `PipelinePhase` | `"idle" \| "spec" \| "analyze" \| "architect" \| "plan" \| "build" \| "done" \| "stopped" \| "needs_attention" \| "error"` |
| `StoryStatus` | `"todo" \| "in_progress" \| "red" \| "green" \| "done" \| "failed"` |
| `BuildStage` | `"queued" \| "analyzing" \| "contracts" \| "implementing" \| "verifying" \| "merge_wait" \| "merging" \| "done" \| "failed"` (miroir enum backend ; `merging` = transitoire possible) |
| `ChatRole` | `"user" \| "pm" \| "po" \| "dev" \| "analyst" \| "architect" \| "qa" \| "critic" \| "judge" \| "system"` |
| `TestState` | `"nonexistent" \| "red" \| "green"` |
| `HypothesisStatus` | `"proposed" \| "selected" \| "done" \| "rejected"` |
| `ComponentStatus` | `"proposed" \| "approved" \| "created" \| "rejected"` |
| `StreamKind` | `"backend" \| "frontend" \| "cache" \| "database" \| "other"` |
| `StallReason` | `string` — `"" \| "merge_lock_held:<id>" \| "awaiting_approval" \| "budget_paused"` |
| `MergeState` (types.ts) | `"merged" \| "conflict" \| "none"` |

### 5.2 Interfaces

**`RecoveryState`** : `attempt: number` ; `max_attempts: number` ; `kind: string` (`"" | "refining" | "critic_restored" | "regression_rerun" | "mutation_rerun" | "retry"`).

**`GuidanceEntry`** (P10) : `id: string` ; `text: string` ; `ts: number` ; `status: string` (`"queued" | "applied" | "too_late"`).

**`PlannedTest`** : `id`, `layer`, `description`: string ; `mocks: string[]` ; `file_hint: string` ; `criteria: string[]` (ids de critères) ; `status: TestState`.

**`AcceptanceCriterion`** : `id: string` ; `text: string`.

**`ProductComponent`** : `id`, `kind` (backend | frontend | database | cache | other), `name`, `technology`, `rationale`: string ; `optional: boolean` ; `status: ComponentStatus`.

**`RunnerCapabilities`** : `can_edit_files`, `can_run_shell`, `supports_native_skills`, `reliable_for_build`: boolean ; `execution_model: string` ; `notes?: string`.

**`ProviderInfo`** : `provider: string` ; `model: string` ; `available: string[]` ; `models: Record<string, string[]>` (suggestions par provider, alimente le 2e dropdown adaptatif) ; `capabilities?: RunnerCapabilities`.

**`Finding`** (E6, évaluateur produit) : `id: string` ; `severity: string` (low | medium | high) ; `kind: string` (bug | integration | ux | gap) ; `title`, `detail`: string ; `iteration: number`.

**`FeatureHypothesis`** : `id`, `title`, `rationale`: string ; `value`, `complexity`: number ; `status: HypothesisStatus` ; `rank: number`.

**`ChatMessage`** : `role: ChatRole` ; `content: string` ; `ts: number`.

**`Stream`** (ST-1) : `id: string` ; `kind: StreamKind` ; `language`, `toolchain`, `file_root`: string ; `primary: boolean`.

**`Task`** (ST-2) : `id`, `story_id`: string ; `stream: string` (`""` = stream primaire/backend) ; `title`, `description`: string ; `acceptance_criteria: AcceptanceCriterion[]` ; `gherkin: string` ; `depends_on: string[]` (ids de Tasks, potentiellement cross-stream) ; `status: StoryStatus` ; `attempts: number` ; `last_error: string` ; `files_hint: string[]` ; télémétrie BUILD optionnelle (B1) : `current_stage?: BuildStage` ; `stage_started_at?: number` (epoch s, 0 = jamais démarré) ; `current_persona?: string` (`"qa" | "dev" | "critic" | ""`) ; `recovery?: RecoveryState` ; `guidance?: GuidanceEntry[]`.

**`UserStory`** : `id`, `epic_id`, `title`, `description`: string ; `acceptance_criteria: AcceptanceCriterion[]` ; `gherkin: string` ; `test_plan: PlannedTest[]` ; `depends_on: string[]` ; `priority: number` ; `status: StoryStatus` ; `effective_status_value?: StoryStatus` ; `iteration: number` ; `attempts: number` ; `last_error: string` ; `quality_score: number` ; `mutation_score?: number` ; `coverage_score?: number` ; `ui?: boolean` ; `ui_tests?: string[]` ; `stream?: string` ; `tasks?: Task[]` (non vide ⇒ US conteneur, statut dérivé) ; Technical Story : `technical?: boolean` ; `contract?: string` (remplace le Gherkin fonctionnel) ; `parent_id?: string` (US/TS d'extraction) ; + la même télémétrie BUILD optionnelle que `Task` (`current_stage?`, `stage_started_at?`, `current_persona?`, `recovery?`, `guidance?`).

**`Epic`** : `id`, `title`, `description`: string ; `iteration: number`.

**`Usage`** : `cost_usd`, `input_tokens`, `output_tokens`, `agent_calls`: number.

**`ProjectState`** (état complet d'un projet, diffusé par SSE) :

| Champ | Type | Note |
|---|---|---|
| `id`, `name`, `goal` | `string` | |
| `auto_spec` | `boolean` | |
| `product_profile?` | `"auto" \| "library-fast" \| "cli" \| "api" \| "web-ssr" \| "fullstack" \| "brownfield"` | |
| `spec_mode` | `"interview" \| "brainstorm"` | |
| `phase` | `PipelinePhase` | |
| `brief` | `string` | |
| `idea_maturity?` | `"" \| "structured" \| "vague"` | B-IDEA |
| `idea_rationale?` | `string` | |
| `brainstorm_techniques?` | `string[]` | |
| `awaiting_brainstorm_decision?` | `boolean` | |
| `streams?` | `Stream[]` | vide/absent = 1 stream backend implicite (legacy) |
| `backlog` | `FeatureHypothesis[]` | |
| `components?` | `ProductComponent[]` | |
| `epics` | `Epic[]` | |
| `stories` | `UserStory[]` | |
| `chat` | `ChatMessage[]` | |
| `feedback` | `string[]` | |
| `findings?` | `Finding[]` | E6 |
| `lessons?` | `string[]` | E7 |
| `retro_recommendations?` | `string[]` | E7 |
| `iteration` | `number` | |
| `running` | `boolean` | app générée en cours d'exécution |
| `paused` | `boolean` | |
| `awaiting_approval?` | `string` | |
| `regressions?` | `string[]` | |
| `resume_at?` | `number` | epoch de reprise auto programmée (0 = aucune) — M2 |
| `error` | `string` | |
| `created_at` | `number` | |
| `architecture` | `string` | |
| `plan_quality` | `number` | |
| `plan_review_issues?` / `plan_review_suggestions?` | `string[]` | |
| `backend_language?` | `"python" \| "go" \| "rust"` | |
| `language_complexity?` / `language_criticality?` | `number` | |
| `language_rationale?` | `string` | |
| `usage` | `Usage` | total projet |
| `iteration_usage?` | `Record<string, Usage>` | clé = n° d'itération (string en JSON) |
| `budget_usd` | `number` | |
| `archived` | `boolean` | |
| `delivery_ready?` | `boolean` | |
| `delivery_issues?` | `string[]` | |

**`LogLine`** : `source: string` ; `line: string`.

**`AgentInteraction`** (O2, fetch à la demande, jamais dans `ProjectState`) : `id`, `item_id`, `phase`, `persona`, `prompt`, `response`: string ; `ok: boolean` ; `error: string` ; `input_tokens`, `output_tokens`, `cost_usd`, `duration_ms`: number ; `prompt_truncated`, `response_truncated`: boolean ; `ts: number`.

**`TickItem`** (B-UX, entrée item d'un heartbeat) : `id: string` ; `kind: "story" | "task"` ; `status: string` ; `current_stage: string` (valeur `BuildStage`) ; `stage_started_at: number` ; `current_persona: string` ; `recovery: RecoveryState`.

**`TickCounts`** : `running`, `queued`, `done`, `failed`, `blocked`: number. (Mapping : IN_PROGRESS/RED/GREEN → running ; DONE → done ; FAILED → failed ; TODO deps non satisfaites → blocked ; TODO sinon → queued.)

**`ProjectTicks`** (stockage client du heartbeat d'UN projet) : `ts: number` ; `items: Record<string, TickItem>` (clé = id d'item) ; `counts: TickCounts` ; `stallReason: StallReason`.

**`WsEvent`** (union discriminée sur `type`) :

```ts
export type WsEvent =
  | { type: "state"; project_id: string; state: ProjectState }
  | { type: "log"; project_id: string; source: string; line: string }
  | { type: "deleted"; project_id: string }
  | { type: "notify"; project_id: string; level: string; title: string; body: string }
  | { type: "tick"; project_id: string; ts: number; items: TickItem[];
      counts: TickCounts; stall_reason: StallReason };
```

**`StoryPatch`** (édition de story, tous champs optionnels) : `title?`, `description?`, `gherkin?`: string ; `priority?: number` ; `acceptance_criteria?: { id?: string; text: string }[]`.

**`NewStoryBody`** : `epic_id: string` ; `title: string` ; `description?`, `gherkin?`: string ; `priority?: number` ; `acceptance_criteria?: string[]` ; `depends_on?: string[]`.

**`FileListing`** : `files: string[]` (chemins POSIX relatifs, triés). **`FileContent`** : `path: string` ; `content: string` ; `truncated: boolean`. **`StoryDiff`** : `ok`, `available`: boolean ; `diff: string`.

**`Metrics`** : `projects`, `total_cost_usd`, `total_tokens`, `total_agent_calls`, `total_stories`, `stories_done`, `stories_failed`, `success_rate`, `avg_attempts`, `cost_per_story`: number ; `avg_quality`, `avg_mutation`, `avg_coverage`: `number | null` ; `findings`, `regressions`: number.

### 5.3 Fonctions exportées dans types.ts

- **`criterionState(story, criterion): TestState`** : `story.status === "done"` → `"green"` ; sinon filtre `story.test_plan` sur `t.criteria.includes(criterion.id)` : un test `red` → `"red"` ; tous verts (et ≥1) → `"green"` ; sinon `"nonexistent"`.
- **`usEffectiveStatus(story): StoryStatus`** (ST-12) : `effective_status_value` s'il existe ; sinon sans tasks → `story.status` ; sinon dérivé des tasks : toutes `done` → `done` ; au moins une `in_progress|red|green` → `in_progress` ; au moins une `failed` → `failed` ; sinon `todo`.
- **`mergeState(status, lastError = ""): MergeState`** (ST-14) : `done` → `"merged"` ; `failed` + `lastError` matche `/conflit de merge|merge conflict/i` → `"conflict"` ; sinon `"none"`.
- **`blockedBy(dependsOn, status, stories): string[]`** (ST-14) : `[]` si `status !== "todo"` ; sinon ids de `depends_on` dont la cible (task ou US via `usEffectiveStatus`) n'est pas `done` ; cible inconnue = non bloquante.

⚠️ `types.ts` et `work.ts` exportent chacun `mergeState` et `blockedBy` avec des signatures **différentes** (voir §6) — attention aux imports lors de la recréation.

---

## 6. `work.ts` — logique métier dérivée (miroir du backend)

Module **pur, sans dépendances** (miroir frontend de `orchestrator/streams.py` et `UserStory.effective_status` de `models.py`), unit-testé dans `work.test`. Permet au Board multi-stream (ST-12/13/14) de dériver statut effectif, blocages et état de merge sans aller-retour serveur.

### 6.1 Stepper de stages BUILD (B-UX)

- **`STAGE_ORDER: BuildStage[]`** = `["queued", "analyzing", "contracts", "implementing", "verifying", "merge_wait", "merging", "done"]` — ordre gauche→droite du Stepper ; `done`/`failed` partagent le slot terminal.
- **`stageIndex(stage: string): number`** : index dans `STAGE_ORDER` ; `"failed"` → dernier index ; inconnu/vide → 0.
- **`isStageDone(cell, current): boolean`** : `current === "done"` → true ; `"failed"` → false ; sinon `stageIndex(current) > stageIndex(cell)`.
- **`isStageActive(cell, current): boolean`** : false si done/failed ; sinon égalité stricte d'index **et** de valeur.
- **`elapsedLabel(startedAt: number | undefined, now: number): string`** : durée humaine depuis `startedAt` (epoch s) mesurée à `now` (epoch ms) — `""` si non démarré ou skew ; formats `"{s}s"`, `"{m}m {s}s"`, `"{h}h {m}m"`.

### 6.2 Vue d'item fusionnée state + tick

- **`interface ItemView`** : `id: string` ; `kind: "story" | "task"` ; `status: StoryStatus` ; `stage: BuildStage` ; `stageStartedAt: number` ; `persona: string` ; `recovery: RecoveryState` ; `guidance: GuidanceEntry[]` ; `fromTick: boolean`.
- **`deriveItemView(item: UserStory | Task, tick?: TickItem): ItemView`** : `kind` déduit par `"epic_id" in item`. Règle clé : un item **terminal** (`done`/`failed`) est autoritaire depuis l'état **persisté** (un tick périmé — boucle ~10 s — ne doit jamais re-basculer un item terminé en « in progress ») ; pour un item non terminal, le tick gagne pour status/stage/stageStartedAt/persona/recovery. `guidance` vient **toujours** du persisté (jamais dans le tick). Constante `EMPTY_RECOVERY = { attempt: 0, max_attempts: 0, kind: "" }`.

### 6.3 Statut effectif et reprise de build

- **`effectiveStatus(story): StoryStatus`** : identique à `usEffectiveStatus` de types.ts (dupliqué ici).
- **`DORMANT_PHASES: PipelinePhase[]`** = `["done", "stopped", "needs_attention", "error"]` — phases dormantes où un build en pause peut reprendre. `done` DOIT y figurer (une itération auto-spec terminée laisse le projet en `done` avec des stories non construites — son omission fut la régression « Continuer le build »). Source de vérité unique.
- **`hasBuildableStory(stories?): boolean`** : au moins une story dont le statut **effectif** ∈ `{todo, red, in_progress, green}` (en phase dormante, un `in_progress`/`green` est un orphelin de crash — le backend le remet à TODO à la reprise via `_reset_orphan_items`).
- **`canResumeBuild(project): boolean`** : `DORMANT_PHASES.includes(project.phase) && hasBuildableStory(project.stories)` — **prédicat unique** gérant l'affordance « Continuer le build », partagé par RunPanel et ProjectBar (le backend `aresume_build` reste l'autorité et répond 409 en cas d'abus).

### 6.4 Graphe d'items de travail

- **`interface WorkItem`** : `id: string` ; `kind: "task" | "story"` ; `storyId: string` ; `stream: string` ; `title: string` ; `status: StoryStatus` ; `dependsOn: string[]` (résolus vers d'autres ids d'items).
- **`primaryStreamId(streams): string`** : le stream `primary`, sinon le premier `kind === "backend"`, sinon `streams[0]?.id ?? "backend"`. C'est l'id que résout toute référence de stream vide `""`.
- **`buildWorkGraph(stories, streams): Map<string, WorkItem>`** (miroir de `build_work_graph` backend) : une US sans tasks = 1 item ; une US décomposée = 1 item par task. Résolution des dépendances : dep vers une task → elle-même ; dep vers une US → tous ses « leaf task ids » (récursif via `parent_id` pour les Technical Stories : dépendre d'un conteneur = dépendre des tasks de ses TS enfants), ou l'US elle-même si aucune leaf ; dep inconnue → abandonnée (comme le backend) ; self-dep et doublons filtrés ; une task hérite des deps de son US.
- **`blockedBy(itemId, items): string[]`** (ST-14, signature ≠ types.ts) : deps présentes dans le graphe et non `done`. Vide = prêt/débloqué.
- **`type MergeState = "merged" | "conflict" | null`** et **`mergeState(status, lastError?)`** (≠ types.ts : `null` au lieu de `"none"`, et test `lastError.toLowerCase().includes("merge")`).

### 6.5 Streams et layout du graphe

- **`effectiveStreams(streams: Stream[] | undefined, backendLanguage = "python"): Stream[]`** : streams déclarés, sinon un stream backend implicite `{ id: "backend", kind: "backend", language: backendLanguage, toolchain: "", file_root: "", primary: true }` (legacy/flag-off).
- **`hasMultiStream(streams, stories): boolean`** : `(streams?.length ?? 0) > 1 || une story a des tasks` — sinon look legacy du Board.
- **`streamIcon(kind: string): string`** : `{ backend: "⚙️", frontend: "🎨", cache: "⚡", database: "🗄️", other: "🔧" }`, fallback `other`.
- **`interface GraphLayout`** : `layer: Map<string, number>` (id → colonne) ; `maxLayer: number` ; `critical: Set<string>` (ids sur UN chemin critique) ; `maxParallel: number` (largeur max de couche = parallélisme de pointe).
- **`computeGraphLayout(items): GraphLayout`** : colonne = plus long chemin depuis une source (DFS mémoïsé avec garde de cycle défensive via un set `visiting`) ; chemin critique reconstruit depuis le nœud le plus profond en suivant à chaque pas la dépendance la plus profonde ; `maxParallel` = max des effectifs par couche.

---

## 7. i18n (et thème)

### 7.1 Mécanisme (`src/i18n/i18n.ts`)

- **Langues** : `type Lang = "en" | "fr"` ; `LANGS = [{ value: "en", label: "English", flag: "🇬🇧" }, { value: "fr", label: "Français", flag: "🇫🇷" }]`. Défaut : **`"en"`**.
- **Persistance** : `localStorage` clé **`"autospec.lang"`** (try/catch — repli défaut si indisponible). `setLang` pose aussi `lang` sur `<html>` ; `initLang()` l'applique au boot (appelé dans main.tsx).
- **Store module-level** (PAS de Context React) : variable `currentLang` + `Set` de `listeners`. Exporte `getLang()`, `setLang(lang)` (no-op si inchangée ; persiste, met à jour `<html lang>`, notifie), `subscribeLang(fn)` (retourne l'unsubscribe). Avantage : `t()` marche **partout**, y compris hors composants.
- **`t(key, vars?)`** : lookup dans le dictionnaire plat `messages[key]` ; repli gracieux **langue courante → anglais → la clé elle-même** (une entrée manquante est visible mais ne crashe jamais). `vars` interpole les placeholders `{name}` via `str.replace(new RegExp(\`\\{${k}\\}\`, "g"), String(v))`.
- **`useI18n(): { t, lang, setLang }`** : hook qui force un re-render au changement de langue (`useReducer` compteur + `useEffect(() => subscribeLang(force), [])`). Consommation type : `const { t } = useI18n(); … t("app.subtitle")`.

### 7.2 Structure des messages (`src/i18n/messages/`)

- **`index.ts`** : registre central. Types `Entry = { en: string; fr: string }` et `Namespace = Record<string, Entry>`. Chaque namespace vit dans **son propre fichier** (évite les collisions d'édition parallèle). L'index importe 21 namespaces : `app`, `common`, `settings`, `projectBar`, `projectSetup`, `runPanel`, `board`, `activity`, `llmActivity`, `chatPanel`, `componentsPanel`, `languagePanel`, `backlogPanel`, `architecturePanel`, `planReviewPanel`, `dashboard`, `workspaceViews`, `depGraph`, `iterationsView`, `stepper`, `codeViewer`, `collapsible` — et les aplatit en `messages["<namespace>.<clé>"] = entry`.
- **Forme d'un fichier de messages** (ex. `common.ts`) :

```ts
import type { Namespace } from "./index";

export const common: Namespace = {
  close: { en: "Close", fr: "Fermer" },
  cancel: { en: "Cancel", fr: "Annuler" },
  // …
};
```

- `common.ts` porte les termes génériques réutilisables (close, cancel, save, delete, confirm, yes/no/ok, edit, add, remove, loading, retry, refresh, error, success) — à utiliser via `common.*` plutôt que de re-déclarer par composant.
- `app.ts` porte les clés du shell : `subtitle`, `providerTitle`, `providerDemo`, `provider`, `model`, `modelLive`, `modelSuggested`, `refreshModels(Aria)`, `dashboard`, `settings`, `closeError`, `closeNotification`, `closeSetup`, `placeholder`, `confirmDelete`, `confirmRollback`, `rollbackToastTitle/Body`, `confirmRestartScratch`, `restartToastTitle/Body`, `deployToastTitle/Artifacts/None`, `commitToastTitle/Body` — avec placeholders `{name}`, `{n}`, `{list}`, `{commit}`.

### 7.3 Thème (`src/i18n/theme.ts`, même patron que la langue)

- `type Theme = "dark" | "light"`, défaut **`"dark"`**, persistance `localStorage` clé **`"autospec.theme"`**.
- Application : `document.documentElement.setAttribute("data-theme", theme)` — les variables CSS vivent sous `:root[data-theme="dark|light"]`.
- Exporte `getTheme()`, `setTheme()`, `toggleTheme()`, `subscribeTheme()`, `initTheme()` (boot, appelé dans main.tsx) et le hook `useTheme(): { theme, setTheme, toggleTheme }` (même mécanique `useReducer` + subscribe).
