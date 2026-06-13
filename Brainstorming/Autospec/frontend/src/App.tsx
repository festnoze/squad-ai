import { useEffect, useMemo, useRef, useState } from "react";
import {
  archiveProject,
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
  resumeProject,
  runProject,
  sendChat,
  setProvider,
  setSpecMode,
  setupComponents,
  stopApp,
  stopProject,
  unarchiveProject,
  updateComponents,
} from "./api";
import { ArchitecturePanel } from "./components/ArchitecturePanel";
import { BacklogPanel } from "./components/BacklogPanel";
import { Board } from "./components/Board";
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

export default function App() {
  const [projects, setProjects] = useState<ProjectState[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showSetup, setShowSetup] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [logs, setLogs] = useState<StampedLog[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [provider, setProviderInfo] = useState<ProviderInfo | null>(null);
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
      },
    );
  }, []);

  const handleCreate = async (
    goal: string,
    name: string,
    autoSpec: boolean,
    budgetUsd: number,
  ) => {
    setBusy(true);
    setError("");
    try {
      const { state } = await createProject(goal, name, autoSpec, budgetUsd);
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

  return (
    <div className="app">
      <header>
        <h1>
          ⚙️ Autospec <span className="subtitle">PM → PO → QA → Dev, en BDD/TDD (BMAD method)</span>
        </h1>
        {provider && (
          <div className="provider-select" title="Provider d'agents (Claude / OpenAI / Ollama)">
            <span className="provider-label">🤖</span>
            <select
              value={provider.provider}
              disabled={provider.provider === "fake"}
              onChange={(e) => handleProviderChange(e.target.value)}
            >
              {provider.provider === "fake" && <option value="fake">démo</option>}
              {provider.available.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
            <span className="provider-model">{provider.model}</span>
          </div>
        )}
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
            />
            <ComponentsPanel
              components={project.components ?? []}
              onUpdate={(components: ProductComponent[]) =>
                guard(() => updateComponents(project.id, components))()
              }
              onSetup={guard(() => setupComponents(project.id))}
            />
            <BacklogPanel backlog={project.backlog ?? []} />
            <ArchitecturePanel
              architecture={project.architecture ?? ""}
              planQuality={project.plan_quality ?? -1}
            />
          </div>
          <div className="col-right">
            <Board
              epics={project.epics ?? []}
              stories={project.stories ?? []}
              projectId={project.id}
            />
            <RunPanel
              project={project}
              logs={projectLogs}
              onRun={guard(() => runProject(project.id))}
              onStop={guard(() => stopProject(project.id))}
              onPause={guard(() => pauseProject(project.id))}
              onResume={guard(() => resumeProject(project.id))}
              onStopApp={guard(() => stopApp(project.id))}
              onResumeBuild={guard(() => resumeBuild(project.id))}
              onDocument={guard(() => documentProject(project.id))}
              onExportZip={() => window.open(exportZipUrl(project.id), "_blank")}
              onGitExport={guard(async () => {
                const { commit } = await gitExportProject(project.id);
                window.alert(`Workspace commité : ${commit.slice(0, 12)}`);
              })}
            />
            <CodeViewer projectId={project.id} />
          </div>
        </main>
      )}
    </div>
  );
}
