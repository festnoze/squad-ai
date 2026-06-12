import { useEffect, useMemo, useRef, useState } from "react";
import {
  archiveProject,
  connectEvents,
  createProject,
  deleteProject,
  listProjects,
  pauseProject,
  resumeBuild,
  resumeProject,
  runProject,
  sendChat,
  stopApp,
  stopProject,
  unarchiveProject,
} from "./api";
import { ArchitecturePanel } from "./components/ArchitecturePanel";
import { BacklogPanel } from "./components/BacklogPanel";
import { Board } from "./components/Board";
import { ChatPanel } from "./components/ChatPanel";
import { CodeViewer } from "./components/CodeViewer";
import { ProjectBar } from "./components/ProjectBar";
import { ProjectSetup } from "./components/ProjectSetup";
import { RunPanel } from "./components/RunPanel";
import { ProjectState, WsEvent } from "./types";

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
        if (firstVisible) setSelectedId(firstVisible.id);
        else setShowSetup(true);
      })
      .catch(() => setShowSetup(true));
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
          .catch((e) => setError(String(e)));
      },
    );
  }, []);

  const handleCreate = async (goal: string, name: string, autoSpec: boolean) => {
    setBusy(true);
    setError("");
    try {
      const { state } = await createProject(goal, name, autoSpec);
      upsert(state);
      setSelectedId(state.id);
      setShowSetup(false);
    } catch (e) {
      setError(String(e));
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
      setProjects((prev) => {
        const remaining = prev.filter((p) => p.id !== target.id);
        if (target.id === selectedId) {
          setSelectedId(remaining[0]?.id ?? null);
          if (remaining.length === 0) setShowSetup(true);
        }
        return remaining;
      });
      setLogs((prev) => prev.filter((l) => l.projectId !== target.id));
    } catch (e) {
      setError(String(e));
    }
  };

  const handleArchive = async (target: ProjectState) => {
    try {
      await archiveProject(target.id);
    } catch (e) {
      setError(String(e));
    }
  };

  const handleUnarchive = async (target: ProjectState) => {
    try {
      await unarchiveProject(target.id);
    } catch (e) {
      setError(String(e));
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

  const guard = (fn: () => Promise<void>) => () => fn().catch((e) => setError(String(e)));

  const projectLogs = useMemo(
    () => logs.filter((l) => l.projectId === selectedId),
    [logs, selectedId],
  );

  const showHome = showSetup || (!project && visibleProjects.length === 0);

  return (
    <div className="app">
      <header>
        <h1>
          ⚙️ Autospec <span className="subtitle">PM → PO → QA → Dev, en BDD/TDD (BMAD method)</span>
        </h1>
      </header>
      {(visibleProjects.length > 0 || projects.some((p) => p.archived)) && (
        <ProjectBar
          projects={projects}
          selectedId={showHome ? null : selectedId}
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
        />
      )}
      {error && <div className="error-banner">{error}</div>}
      {showHome || !project ? (
        <main className="home">
          <ProjectSetup onCreate={handleCreate} busy={busy} />
        </main>
      ) : (
        <main className="workspace">
          <div className="col-left">
            <ChatPanel
              chat={project.chat}
              phase={project.phase}
              onSend={(m) => guard(() => sendChat(project.id, m))()}
            />
            <BacklogPanel backlog={project.backlog} />
            <ArchitecturePanel
              architecture={project.architecture}
              planQuality={project.plan_quality}
            />
          </div>
          <div className="col-right">
            <Board epics={project.epics} stories={project.stories} projectId={project.id} />
            <RunPanel
              project={project}
              logs={projectLogs}
              onRun={guard(() => runProject(project.id))}
              onStop={guard(() => stopProject(project.id))}
              onPause={guard(() => pauseProject(project.id))}
              onResume={guard(() => resumeProject(project.id))}
              onStopApp={guard(() => stopApp(project.id))}
              onResumeBuild={guard(() => resumeBuild(project.id))}
            />
            <CodeViewer projectId={project.id} />
          </div>
        </main>
      )}
    </div>
  );
}
