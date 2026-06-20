import { useEffect, useMemo, useRef, useState } from "react";
import {
  archiveProject,
  cancelResume,
  connectEvents,
  createProject,
  deleteProject,
  documentProject,
  errorMessage,
  exportZipUrl,
  getProvider,
  gitExportProject,
  listProjects,
  pauseProject,
  resumeBuild,
  retryFailed,
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
import { ProductComponent, ProjectState, ProviderInfo, WsEvent } from "./types";

interface StampedLog {
  projectId: string;
  source: string;
  line: string;
}

interface NotifyToast {
  id: number;
  level: string;
  title: string;
  body: string;
}

export default function App() {
  const [projects, setProjects] = useState<ProjectState[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showSetup, setShowSetup] = useState(false);
  const [showDashboard, setShowDashboard] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [logs, setLogs] = useState<StampedLog[]>([]);
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
  const providerRef = useRef<HTMLDivElement>(null);
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
      next[i] = state;
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
    if (!window.confirm(`Supprimer le projet « ${target.name} » et tout son code généré ?`))
      return;
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
    if (!window.confirm(`Revenir à l'itération ${n} ? Le workspace sera restauré à ce snapshot.`))
      return;
    await guard(() => rollbackProject(project.id, n))();
    pushToast("success", "Rollback", `Revenu à l'itération ${n}.`);
  };

  return (
    <div className="app">
      <header>
        <h1>
          ⚙️ Autospec <span className="subtitle">PM → PO → QA → Dev, en BDD/TDD (BMAD method)</span>
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
              title="Provider & modèle d'agents (Claude / OpenAI / Ollama / Anthropic)"
            >
              🤖 {provider.provider === "fake" ? "démo" : provider.provider}
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
                  <span>Provider</span>
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
                  <span>Modèle</span>
                  <select
                    value={provider.model}
                    onChange={(e) => handleModelChange(e.target.value)}
                  >
                    {/* Le modèle courant peut ne pas figurer dans la liste
                        suggérée (ex. « (défaut CLI) ») : on l'ajoute en tête. */}
                    {provider.model &&
                      !(provider.models[provider.provider] ?? []).includes(provider.model) && (
                        <option value={provider.model}>{provider.model}</option>
                      )}
                    {(provider.models[provider.provider] ?? []).map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            )}
          </div>
        )}
        <button
          className="dash-btn"
          onClick={() => setShowDashboard(true)}
          title="Dashboard de l'usine"
          aria-label="Dashboard de l'usine"
        >
          📊
        </button>
      </header>
      {(visibleProjects.length > 0 || projects.some((p) => p.archived)) && (
        <ProjectBar
          projects={projects}
          selectedId={showSetup ? null : selectedId}
          onSelect={(id) => {
            setSelectedId(id);
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
            title="Fermer le message d'erreur"
            aria-label="Fermer le message d'erreur"
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
          {toasts.map((t) => (
            <div key={t.id} className={`toast toast-${t.level}`}>
              <div className="toast-text">
                <div className="toast-title">{t.title}</div>
                {t.body && <div className="toast-body">{t.body}</div>}
              </div>
              <button
                type="button"
                className="toast-close"
                aria-label="Fermer la notification"
                onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
      {showDashboard && <Dashboard onClose={() => setShowDashboard(false)} />}
      {showSetup && (
        <div
          className="modal-backdrop"
          onClick={() => canCloseSetup && setShowSetup(false)}
        >
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            {canCloseSetup && (
              <button
                className="modal-close"
                title="Fermer"
                aria-label="Fermer la création de projet"
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
            <div className="placeholder">
              Sélectionne un projet dans la barre ci-dessus, ou crée-en un avec « ＋ Nouveau ».
            </div>
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
              projectId={project.id}
              phase={project.phase}
              iterationUsage={project.iteration_usage}
              onRollbackTo={handleRollbackTo}
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
              onDocument={guard(() => documentProject(project.id))}
              onCancelResume={guard(() => cancelResume(project.id))}
              onApprove={guard(() => approveProject(project.id))}
              onReject={guard(() => rejectProject(project.id))}
              onDeploy={guard(async () => {
                if (!project) return;
                const { created } = await deployProject(project.id);
                pushToast(
                  "success",
                  "Déploiement",
                  created.length
                    ? `Artefacts générés : ${created.join(", ")}`
                    : "Artefacts de déploiement déjà présents.",
                );
              })}
              onExportZip={() => window.open(exportZipUrl(project.id), "_blank")}
              onGitExport={guard(async () => {
                const { commit } = await gitExportProject(project.id);
                pushToast("success", "Commit", `Workspace commité : ${commit.slice(0, 12)}`);
              })}
            />
            <CodeViewer projectId={project.id} />
          </div>
        </main>
      )}
    </div>
  );
}
