import { useEffect, useMemo, useRef, useState } from "react";
import {
  archiveProject,
  cancelResume,
  connectEvents,
  createProject,
  deleteProject,
  documentProject,
  errorMessage,
  interruptProject,
  exportZipUrl,
  discoverModels,
  getProvider,
  gitExportProject,
  listProjects,
  pauseProject,
  resumeBuild,
  retryFailed,
  restartFromScratch,
  resumeProject,
  resolveBrainstorm,
  approveProject,
  rejectProject,
  rollbackProject,
  deployProject,
  runProject,
  sendChat,
  setProvider,
  setSpecMode,
  setLanguage,
  setupComponents,
  stopApp,
  stopProject,
  unarchiveProject,
  updateComponents,
} from "./api";
import { ArchitecturePanel } from "./components/ArchitecturePanel";
import { LanguagePanel } from "./components/LanguagePanel";
import { BacklogPanel } from "./components/BacklogPanel";
import { WorkspaceViews } from "./components/WorkspaceViews";
import { Dashboard } from "./components/Dashboard";
import { ChatPanel } from "./components/ChatPanel";
import { CodeViewer } from "./components/CodeViewer";
import { ComponentsPanel } from "./components/ComponentsPanel";
import { ProjectBar } from "./components/ProjectBar";
import { ProjectSetup } from "./components/ProjectSetup";
import { RunPanel } from "./components/RunPanel";
import { SettingsModal } from "./components/SettingsModal";
import { Logo } from "./components/Logo";
import { useI18n } from "./i18n/i18n";
import {
  GuidanceEntry,
  ProductComponent,
  ProjectState,
  ProjectTicks,
  ProviderInfo,
  Task,
  UserStory,
  WsEvent,
} from "./types";

interface StampedLog {
  projectId: string;
  source: string;
  line: string;
}

/**
 * B-UX: merge guidance arrays by id so a full `state` event never clobbers an
 * optimistic local entry that the server hasn't persisted yet. Server status
 * wins for ids it knows; optimistic-only entries (not yet echoed back) are
 * preserved. Applied across every story and task of the incoming state.
 */
function mergeGuidance(
  incoming: GuidanceEntry[] | undefined,
  prev: GuidanceEntry[] | undefined,
): GuidanceEntry[] | undefined {
  if (!prev || prev.length === 0) return incoming;
  const next = [...(incoming ?? [])];
  const byId = new Map(next.map((g) => [g.id, g]));
  for (const g of prev) {
    if (!byId.has(g.id)) next.push(g); // optimistic entry the server hasn't echoed yet
  }
  return next;
}

/** B-UX: produce a copy of `state` whose stories'/tasks' guidance arrays are
 * merged with the previously held ones (see mergeGuidance). */
function mergeStateGuidance(state: ProjectState, prev: ProjectState | undefined): ProjectState {
  if (!prev) return state;
  const prevStoryById = new Map((prev.stories ?? []).map((s) => [s.id, s]));
  const prevTaskById = new Map<string, Task>();
  for (const s of prev.stories ?? []) for (const t of s.tasks ?? []) prevTaskById.set(t.id, t);
  const stories = (state.stories ?? []).map((s: UserStory) => {
    const ps = prevStoryById.get(s.id);
    const tasks = s.tasks?.map((t: Task) => ({
      ...t,
      guidance: mergeGuidance(t.guidance, prevTaskById.get(t.id)?.guidance),
    }));
    return { ...s, guidance: mergeGuidance(s.guidance, ps?.guidance), ...(tasks ? { tasks } : {}) };
  });
  return { ...state, stories };
}

interface NotifyToast {
  id: number;
  level: string;
  title: string;
  body: string;
}

export default function App() {
  const { t } = useI18n();
  const [projects, setProjects] = useState<ProjectState[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showSetup, setShowSetup] = useState(false);
  const [showDashboard, setShowDashboard] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [logs, setLogs] = useState<StampedLog[]>([]);
  // B-UX: latest heartbeat data keyed by project id. Never overwrites full
  // project state; refreshes live item-level stage/persona/recovery between
  // `state` snapshots. Cleared (left stale) is harmless — `state` is the source
  // of truth for everything rich.
  const [ticks, setTicks] = useState<Record<string, ProjectTicks>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [toasts, setToasts] = useState<NotifyToast[]>([]);
  const toastIdRef = useRef(0);
  // UI8 : retours d'action in-app (plus de window.alert / prompt natifs).
  const pushToast = (level: NotifyToast["level"], title: string, body = "") => {
    const id = ++toastIdRef.current;
    setToasts((prev) => [...prev.slice(-4), { id, level, title, body }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 6000);
  };
  const [provider, setProviderInfo] = useState<ProviderInfo | null>(null);
  // UI10 : provider + modèle regroupés dans un petit popover compact.
  const [providerMenuOpen, setProviderMenuOpen] = useState(false);
  // Live model discovery per provider (ollama daemon / OpenAI key). Falls back
  // to the static suggested list (provider.models) when discovery is unavailable.
  const [discovered, setDiscovered] = useState<
    Record<string, { models: string[]; source: "live" | "static" }>
  >({});
  const [discovering, setDiscovering] = useState(false);
  const providerRef = useRef<HTMLDivElement>(null);
  const refreshModels = async (name: string) => {
    setDiscovering(true);
    try {
      const res = await discoverModels(name);
      setDiscovered((prev) => ({ ...prev, [name]: { models: res.models, source: res.source } }));
    } catch {
      /* keep the static fallback already in provider.models */
    } finally {
      setDiscovering(false);
    }
  };
  // Discover the current provider's real models when the popover opens.
  useEffect(() => {
    if (providerMenuOpen && provider && provider.provider !== "fake") {
      void refreshModels(provider.provider);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [providerMenuOpen, provider?.provider]);
  useEffect(() => {
    if (!providerMenuOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (providerRef.current && !providerRef.current.contains(e.target as Node)) {
        setProviderMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [providerMenuOpen]);
  // P3 — couple the density axis to the responsive one: below 1200px the shell
  // switches to data-density="compact" (tighter tokens) and reverts above. Pure
  // attribute toggle; the CSS media query carries the actual deltas.
  useEffect(() => {
    const apply = () => {
      document.body.dataset.density =
        window.innerWidth < 1200 ? "compact" : "comfortable";
    };
    apply();
    window.addEventListener("resize", apply);
    return () => window.removeEventListener("resize", apply);
  }, []);
  // Ids des projets supprimés : empêche un event « state » retardé de
  // ressusciter un projet déjà supprimé.
  const deletedIds = useRef<Set<string>>(new Set());

  const project = useMemo(
    () => projects.find((p) => p.id === selectedId) ?? null,
    [projects, selectedId],
  );

  const visibleProjects = useMemo(
    () => (showArchived ? projects : projects.filter((p) => !p.archived)),
    [projects, showArchived],
  );

  const upsert = (state: ProjectState) =>
    setProjects((prev) => {
      const i = prev.findIndex((p) => p.id === state.id);
      if (i === -1) return [state, ...prev];
      const next = [...prev];
      // B-UX: merge guidance by id so a full `state` snapshot doesn't clobber an
      // optimistic local entry the server hasn't echoed back yet.
      next[i] = mergeStateGuidance(state, prev[i]);
      return next;
    });

  useEffect(() => {
    listProjects()
      .then((list) => {
        setProjects(list);
        const firstVisible = list.find((p) => !p.archived);
        // Accueil intelligent : popup de création seulement si AUCUN projet,
        // sinon ouverture directe sur la sélection de projet.
        if (firstVisible) setSelectedId(firstVisible.id);
        else setShowSetup(true);
      })
      .catch((e) => {
        // Backend injoignable : on affiche l'accueil ET l'erreur (pas silencieux).
        setError(errorMessage(e));
        setShowSetup(true);
      });
    // Provider d'agents courant (facultatif : l'UI reste utilisable sans).
    getProvider()
      .then(setProviderInfo)
      .catch(() => setProviderInfo(null));
    // U3 : demande unique de permission des notifications navigateur (best-effort).
    if (typeof Notification !== "undefined" && Notification.permission === "default") {
      void Notification.requestPermission();
    }
  }, []);

  useEffect(() => {
    return connectEvents(
      (event: WsEvent) => {
        if (event.type === "state") {
          // Un event « state » retardé ne doit pas ressusciter un projet supprimé.
          if (deletedIds.current.has(event.state.id)) return;
          upsert(event.state);
        } else if (event.type === "deleted") {
          deletedIds.current.add(event.project_id);
          setProjects((prev) => prev.filter((p) => p.id !== event.project_id));
        } else if (event.type === "log") {
          setLogs((prev) => [
            ...prev.slice(-800),
            { projectId: event.project_id, source: event.source, line: event.line },
          ]);
        } else if (event.type === "tick") {
          // B-UX: heartbeat — store latest per-item data; NEVER overwrite the
          // full project state (titles/criteria/scores live in `state`). A tick
          // for an already-deleted project is ignored.
          if (deletedIds.current.has(event.project_id)) return;
          setTicks((prev) => ({
            ...prev,
            [event.project_id]: {
              ts: event.ts,
              items: Object.fromEntries(event.items.map((it) => [it.id, it])),
              counts: event.counts,
              stallReason: event.stall_reason,
            },
          }));
        } else if (event.type === "notify") {
          const id = ++toastIdRef.current;
          const toast = { id, level: event.level, title: event.title, body: event.body };
          setToasts((prev) => [...prev.slice(-4), toast]);
          if (typeof Notification !== "undefined" && Notification.permission === "granted") {
            try {
              new Notification(event.title, { body: event.body });
            } catch {
              // notification API indisponible : on garde le toast in-app
            }
          }
          setTimeout(
            () => setToasts((prev) => prev.filter((t) => t.id !== id)),
            6000,
          );
        }
      },
      () => {
        // Après une reconnexion, on resynchronise l'état complet : les events
        // émis pendant la coupure sont sinon perdus définitivement.
        listProjects()
          .then((list) => {
            for (const state of list) {
              if (deletedIds.current.has(state.id)) continue;
              upsert(state);
            }
          })
          .catch((e) => setError(errorMessage(e)));
        // Le provider/modèle est récupéré une seule fois au montage : si le
        // backend était down à ce moment-là (sélecteur masqué), on le rafraîchit
        // à la reconnexion pour que le sélecteur réapparaisse sans recharger.
        getProvider()
          .then(setProviderInfo)
          .catch(() => {});
      },
    );
  }, []);

  const handleCreate = async (
    goal: string,
    name: string,
    autoSpec: boolean,
    budgetUsd: number,
    brief?: string,
    brownfieldPath?: string,
  ) => {
    setBusy(true);
    setError("");
    try {
      const { state } = await createProject(goal, name, autoSpec, budgetUsd, brief, brownfieldPath);
      upsert(state);
      setSelectedId(state.id);
      setShowSetup(false);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (target: ProjectState) => {
    if (!window.confirm(t("app.confirmDelete", { name: target.name }))) return;
    try {
      await deleteProject(target.id);
      deletedIds.current.add(target.id);
      // Updater pur (pas de setState imbriqué) : l'effet de repli sur la
      // sélection ci-dessous choisit le prochain projet visible ou l'accueil.
      setProjects((prev) => prev.filter((p) => p.id !== target.id));
      setLogs((prev) => prev.filter((l) => l.projectId !== target.id));
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const handleArchive = async (target: ProjectState) => {
    try {
      await archiveProject(target.id);
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const handleUnarchive = async (target: ProjectState) => {
    try {
      await unarchiveProject(target.id);
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  // Play/stop par chip (U1) : ▶ reprend une pipeline en pause ou relance le
  // build des stories restantes ; ⏹ stoppe la pipeline du projet.
  const handlePlay = async (target: ProjectState) => {
    try {
      if (target.paused) await resumeProject(target.id);
      else await resumeBuild(target.id);
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const handleStop = async (target: ProjectState) => {
    try {
      await stopProject(target.id);
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  // Phases where agents are actively working (chat/dev) — a project in one of
  // these (or with the generated app running) has in-flight work to interrupt.
  const ACTIVE_PHASES = ["spec", "analyze", "plan", "architect", "build"];

  // Switch the selected project. Leaving a RUNNING project hard-interrupts it
  // (kills the in-flight agent CLI call + the generated app) so its chat/dev work
  // doesn't keep running — and spending — once we've navigated away. Fire-and-
  // forget + idempotent: a failure or an already-dormant project is harmless.
  const switchTo = (id: string | null) => {
    if (selectedId && selectedId !== id) {
      const leaving = projects.find((p) => p.id === selectedId);
      if (leaving && (ACTIVE_PHASES.includes(leaving.phase) || leaving.running)) {
        void interruptProject(selectedId).catch(() => undefined);
      }
    }
    setSelectedId(id);
  };

  const handleProviderChange = async (name: string) => {
    try {
      const info = await setProvider(name);
      setProviderInfo((prev) =>
        prev ? { ...prev, provider: info.provider, model: info.model } : prev,
      );
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  // Second (adaptive) dropdown : change le modèle au sein du provider courant.
  const handleModelChange = async (model: string) => {
    if (!provider) return;
    try {
      const info = await setProvider(provider.provider, model);
      setProviderInfo((prev) =>
        prev ? { ...prev, provider: info.provider, model: info.model } : prev,
      );
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  // Keep the selection pointing at a visible project. If the selected project
  // becomes archived (and archived projects are hidden), fall back to the first
  // visible project, or the home screen when none remain.
  useEffect(() => {
    if (selectedId === null) return;
    if (visibleProjects.some((p) => p.id === selectedId)) return;
    const next = visibleProjects[0]?.id ?? null;
    setSelectedId(next);
    if (next === null) setShowSetup(true);
  }, [visibleProjects, selectedId]);

  // Enveloppe une action API : toute erreur remonte dans le bandeau d'erreur.
  const guard = (fn: () => Promise<void>) => () =>
    fn().catch((e) => setError(errorMessage(e)));

  const projectLogs = useMemo(
    () => logs.filter((l) => l.projectId === selectedId),
    [logs, selectedId],
  );

  // La popup de création peut être fermée dès qu'il reste un projet à afficher.
  const canCloseSetup = visibleProjects.length > 0;

  // Rollback déclenché depuis la carte d'une itération (vue Itérations). La
  // disponibilité d'un snapshot est gérée par WorkspaceViews ; ici on confirme
  // et on exécute.
  const handleRollbackTo = async (n: number) => {
    if (!project) return;
    if (!window.confirm(t("app.confirmRollback", { n }))) return;
    await guard(() => rollbackProject(project.id, n))();
    pushToast("success", t("app.rollbackToastTitle"), t("app.rollbackToastBody", { n }));
  };

  // « Relancer from scratch » : destructif (efface code + epics + stories, garde
  // le brief), d'où la confirmation explicite avant l'appel API.
  const handleRestartFromScratch = async () => {
    if (!project) return;
    if (!window.confirm(t("app.confirmRestartScratch", { name: project.name }))) return;
    await guard(() => restartFromScratch(project.id))();
    pushToast("success", t("app.restartToastTitle"), t("app.restartToastBody"));
  };

  return (
    <div className="app">
      <header>
        <h1>
          <Logo /> Autospec <span className="subtitle">{t("app.subtitle")}</span>
        </h1>
        {provider && (
          <div className="provider-control" ref={providerRef}>
            <button
              type="button"
              className="provider-trigger"
              aria-haspopup="menu"
              aria-expanded={providerMenuOpen}
              disabled={provider.provider === "fake"}
              onClick={() => setProviderMenuOpen((o) => !o)}
              title={t("app.providerTitle")}
            >
              🤖 {provider.provider === "fake" ? t("app.providerDemo") : provider.provider}
              <span className="provider-trigger-model"> · {provider.model}</span>
              {provider.provider !== "fake" && (
                <span className="provider-caret" aria-hidden="true">
                  ▾
                </span>
              )}
            </button>
            {providerMenuOpen && provider.provider !== "fake" && (
              <div className="provider-menu" role="menu">
                <label className="provider-field">
                  <span>{t("app.provider")}</span>
                  <select
                    value={provider.provider}
                    onChange={(e) => handleProviderChange(e.target.value)}
                  >
                    {provider.available.map((name) => (
                      <option key={name} value={name}>
                        {name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="provider-field">
                  <span>
                    {t("app.model")}
                    {(() => {
                      const disc = discovered[provider.provider];
                      if (discovering) return <em className="provider-hint"> · …</em>;
                      if (disc?.source === "live")
                        return (
                          <em className="provider-hint provider-hint-live">
                            {" "}
                            · {t("app.modelLive")}
                          </em>
                        );
                      if (disc?.source === "static")
                        return <em className="provider-hint"> · {t("app.modelSuggested")}</em>;
                      return null;
                    })()}
                    <button
                      type="button"
                      className="provider-refresh"
                      title={t("app.refreshModels")}
                      aria-label={t("app.refreshModelsAria")}
                      disabled={discovering}
                      onClick={() => void refreshModels(provider.provider)}
                    >
                      🔄
                    </button>
                  </span>
                  {(() => {
                    // Real models when discovered, else the static suggestions.
                    const modelList =
                      discovered[provider.provider]?.models ??
                      provider.models[provider.provider] ??
                      [];
                    return (
                      <select
                        value={provider.model}
                        onChange={(e) => handleModelChange(e.target.value)}
                      >
                        {/* Le modèle courant peut ne pas figurer dans la liste
                            (ex. « (défaut Codex CLI) ») : on l'ajoute en tête. */}
                        {provider.model && !modelList.includes(provider.model) && (
                          <option value={provider.model}>{provider.model}</option>
                        )}
                        {modelList.map((m) => (
                          <option key={m} value={m}>
                            {m}
                          </option>
                        ))}
                      </select>
                    );
                  })()}
                </label>
              </div>
            )}
          </div>
        )}
        <button
          className="dash-btn"
          onClick={() => setShowDashboard(true)}
          title={t("app.dashboard")}
          aria-label={t("app.dashboard")}
        >
          📊
        </button>
        <button
          className="dash-btn settings-btn"
          onClick={() => setShowSettings(true)}
          title={t("app.settings")}
          aria-label={t("app.settings")}
        >
          ⚙️
        </button>
      </header>
      {(visibleProjects.length > 0 || projects.some((p) => p.archived)) && (
        <ProjectBar
          projects={projects}
          selectedId={showSetup ? null : selectedId}
          onSelect={(id) => {
            switchTo(id);
            setShowSetup(false);
          }}
          onNew={() => setShowSetup(true)}
          onDelete={handleDelete}
          showArchived={showArchived}
          onToggleArchived={() => setShowArchived((v) => !v)}
          onArchive={handleArchive}
          onUnarchive={handleUnarchive}
          onPlay={handlePlay}
          onStop={handleStop}
        />
      )}
      {error && (
        <div
          className="error-banner"
          style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}
        >
          <span>{error}</span>
          <button
            type="button"
            onClick={() => setError("")}
            title={t("app.closeError")}
            aria-label={t("app.closeError")}
            style={{
              background: "transparent",
              border: "none",
              color: "inherit",
              cursor: "pointer",
              padding: "0 2px",
            }}
          >
            ✕
          </button>
        </div>
      )}
      {toasts.length > 0 && (
        <div className="toasts" aria-live="polite">
          {toasts.map((toast) => (
            <div key={toast.id} className={`toast toast-${toast.level}`}>
              <div className="toast-text">
                <div className="toast-title">{toast.title}</div>
                {toast.body && <div className="toast-body">{toast.body}</div>}
              </div>
              <button
                type="button"
                className="toast-close"
                aria-label={t("app.closeNotification")}
                onClick={() => setToasts((prev) => prev.filter((x) => x.id !== toast.id))}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
      {showDashboard && <Dashboard onClose={() => setShowDashboard(false)} />}
      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
      {showSetup && (
        <div
          className="modal-backdrop"
          onClick={() => canCloseSetup && setShowSetup(false)}
        >
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            {canCloseSetup && (
              <button
                className="modal-close"
                title={t("common.close")}
                aria-label={t("app.closeSetup")}
                onClick={() => setShowSetup(false)}
              >
                ✕
              </button>
            )}
            <ProjectSetup onCreate={handleCreate} busy={busy} />
          </div>
        </div>
      )}
      {!project ? (
        <main className="home">
          {!showSetup && (
            <div className="placeholder">{t("app.placeholder")}</div>
          )}
        </main>
      ) : (
        <main className="workspace">
          <div className="col-left">
            {/* `?? défaut` : robustesse face aux anciens états persistés
                auxquels il manque des champs ajoutés depuis. */}
            <ChatPanel
              chat={project.chat ?? []}
              phase={project.phase}
              onSend={(m) => guard(() => sendChat(project.id, m))()}
              specMode={project.spec_mode ?? "interview"}
              onSetSpecMode={(m) => guard(() => setSpecMode(project.id, m))()}
              awaitingBrainstorm={project.awaiting_brainstorm_decision ?? false}
              brainstormTechniques={project.brainstorm_techniques ?? []}
              onResolveBrainstorm={(accept) =>
                guard(() => resolveBrainstorm(project.id, accept))()
              }
            />
            <ComponentsPanel
              components={project.components ?? []}
              onUpdate={(components: ProductComponent[]) =>
                guard(() => updateComponents(project.id, components))()
              }
              onSetup={guard(() => setupComponents(project.id))}
            />
            <LanguagePanel
              language={project.backend_language}
              complexity={project.language_complexity}
              criticality={project.language_criticality}
              rationale={project.language_rationale}
              onSet={(lang) => {
                void guard(() => setLanguage(project.id, lang).then(() => undefined))();
              }}
            />
            <BacklogPanel backlog={project.backlog ?? []} />
            <ArchitecturePanel
              architecture={project.architecture ?? ""}
              planQuality={project.plan_quality ?? -1}
            />
          </div>
          <div className="col-right">
            <WorkspaceViews
              epics={project.epics ?? []}
              stories={project.stories ?? []}
              streams={project.streams}
              projectId={project.id}
              phase={project.phase}
              iterationUsage={project.iteration_usage}
              onRollbackTo={handleRollbackTo}
              ticks={ticks[project.id]}
              awaitingApproval={project.awaiting_approval}
              onApprove={guard(() => approveProject(project.id))}
              onReject={guard(() => rejectProject(project.id))}
            />
            <RunPanel
              project={project}
              logs={projectLogs}
              onRun={(args: string) => guard(() => runProject(project.id, args))()}
              onStop={guard(() => stopProject(project.id))}
              onPause={guard(() => pauseProject(project.id))}
              onResume={guard(() => resumeProject(project.id))}
              onStopApp={guard(() => stopApp(project.id))}
              onResumeBuild={guard(() => resumeBuild(project.id))}
              onRetryFailed={guard(() => retryFailed(project.id))}
              onRestartFromScratch={handleRestartFromScratch}
              onDocument={guard(() => documentProject(project.id))}
              onCancelResume={guard(() => cancelResume(project.id))}
              onApprove={guard(() => approveProject(project.id))}
              onReject={guard(() => rejectProject(project.id))}
              onDeploy={guard(async () => {
                if (!project) return;
                const { created } = await deployProject(project.id);
                pushToast(
                  "success",
                  t("app.deployToastTitle"),
                  created.length
                    ? t("app.deployToastArtifacts", { list: created.join(", ") })
                    : t("app.deployToastNone"),
                );
              })}
              onExportZip={() => window.open(exportZipUrl(project.id), "_blank")}
              onGitExport={guard(async () => {
                const { commit } = await gitExportProject(project.id);
                pushToast(
                  "success",
                  t("app.commitToastTitle"),
                  t("app.commitToastBody", { commit: commit.slice(0, 12) }),
                );
              })}
            />
            <CodeViewer projectId={project.id} />
          </div>
        </main>
      )}
    </div>
  );
}
