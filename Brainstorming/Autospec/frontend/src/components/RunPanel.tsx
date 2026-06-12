import { useEffect, useRef } from "react";
import { LogLine, ProjectState } from "../types";

interface Props {
  project: ProjectState;
  logs: LogLine[];
  onRun: () => void;
  onStop: () => void;
  onPause: () => void;
  onResume: () => void;
  onStopApp: () => void;
  onResumeBuild: () => void;
}

const PHASE_LABEL: Record<string, string> = {
  idle: "En attente",
  spec: "📋 Spécification (PM)",
  analyze: "🔍 Exploration backlog (Analyste)",
  architect: "🏛️ Architecture (design)",
  plan: "🏃 Planification (PO)",
  build: "💻 Développement BDD/TDD",
  done: "✅ Itération terminée",
  stopped: "⏹ Arrêté",
  error: "💥 Erreur",
};

export function RunPanel({ project, logs, onRun, onStop, onPause, onResume, onStopApp, onResumeBuild }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs.length]);

  const canRun = !["spec", "plan", "analyze", "architect", "idle"].includes(project.phase);
  const loopActive = !["done", "stopped", "error"].includes(project.phase);
  const canResumeBuild =
    ["stopped", "error"].includes(project.phase) &&
    project.stories.some((s) => s.status === "todo" || s.status === "red");

  return (
    <div className="panel run">
      <div className="run-header">
        <h2>Exécution</h2>
        <span className={`phase phase-${project.phase}`}>
          {PHASE_LABEL[project.phase]} — itération {project.iteration}
          {project.paused ? " ⏸ en pause" : project.auto_spec && loopActive ? " (boucle auto-spec)" : ""}
        </span>
        <div className="run-buttons">
          <button className="primary" disabled={!canRun || project.running} onClick={onRun}>
            {project.running ? "▶ En cours…" : "▶ Lancer le projet"}
          </button>
          {canResumeBuild && (
            <button
              className="primary"
              onClick={onResumeBuild}
              title="Reprendre la phase build sur les stories restantes"
            >
              ▶ Continuer le build
            </button>
          )}
          {project.running && (
            <button className="danger" onClick={onStopApp} title="Arrêter l'application générée">
              ■ Arrêter l'app
            </button>
          )}
          {loopActive &&
            (project.paused ? (
              <button onClick={onResume} title="Reprendre la pipeline">
                ▶ Reprendre
              </button>
            ) : (
              <button onClick={onPause} title="Mettre la pipeline en pause">
                ⏸ Pause
              </button>
            ))}
          {(loopActive || project.auto_spec) && (
            <button className="danger" disabled={!loopActive} onClick={onStop}>
              ⏹ Stopper
            </button>
          )}
        </div>
      </div>
      <div className="logs">
        {logs.map((l, i) => (
          <div key={i} className="log-line">
            <span className="log-source">[{l.source}]</span> {l.line}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
