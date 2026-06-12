import { useEffect, useMemo, useState } from "react";
import {
  connectEvents,
  createProject,
  deleteProject,
  listProjects,
  runProject,
  sendChat,
  stopProject,
} from "./api";
import { BacklogPanel } from "./components/BacklogPanel";
import { Board } from "./components/Board";
import { ChatPanel } from "./components/ChatPanel";
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
  const [logs, setLogs] = useState<StampedLog[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const project = useMemo(
    () => projects.find((p) => p.id === selectedId) ?? null,
    [projects, selectedId],
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
        if (list.length > 0) setSelectedId(list[0].id);
        else setShowSetup(true);
      })
      .catch(() => setShowSetup(true));
  }, []);

  useEffect(() => {
    return connectEvents((event: WsEvent) => {
      if (event.type === "state") {
        upsert(event.state);
      } else if (event.type === "deleted") {
        setProjects((prev) => prev.filter((p) => p.id !== event.project_id));
      } else if (event.type === "log") {
        setLogs((prev) => [
          ...prev.slice(-800),
          { projectId: event.project_id, source: event.source, line: event.line },
        ]);
      }
    });
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

  const guard = (fn: () => Promise<void>) => () => fn().catch((e) => setError(String(e)));

  const projectLogs = useMemo(
    () => logs.filter((l) => l.projectId === selectedId),
    [logs, selectedId],
  );

  const showHome = showSetup || (!project && projects.length === 0);

  return (
    <div className="app">
      <header>
        <h1>
          ⚙️ Autospec <span className="subtitle">PM → PO → QA → Dev, en BDD/TDD (BMAD method)</span>
        </h1>
      </header>
      {projects.length > 0 && (
        <ProjectBar
          projects={projects}
          selectedId={showHome ? null : selectedId}
          onSelect={(id) => {
            setSelectedId(id);
            setShowSetup(false);
          }}
          onNew={() => setShowSetup(true)}
          onDelete={handleDelete}
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
          </div>
          <div className="col-right">
            <Board epics={project.epics} stories={project.stories} />
            <RunPanel
              project={project}
              logs={projectLogs}
              onRun={guard(() => runProject(project.id))}
              onStop={guard(() => stopProject(project.id))}
            />
          </div>
        </main>
      )}
    </div>
  );
}
