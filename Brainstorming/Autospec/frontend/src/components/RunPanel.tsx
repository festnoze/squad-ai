import { useEffect, useRef } from "react";
import { LogLine, ProjectState } from "../types";

interface Props {
  project: ProjectState;
  logs: LogLine[];
  onRun: () => void;
  onStop: () => void;
}

const PHASE_LABEL: Record<string, string> = {
  idle: "En attente",
  spec: "📋 Spécification (PM)",
  analyze: "🔍 Exploration backlog (Analyste)",
  plan: "🏃 Planification (PO)",
  build: "💻 Développement BDD/TDD",
  done: "✅ Itération terminée",
  stopped: "⏹ Arrêté",
  error: "💥 Erreur",
};

export function RunPanel({ project, logs, onRun, onStop }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs.length]);

  const canRun = !["spec", "plan", "idle"].includes(project.phase);
  const loopActive = !["done", "stopped", "error"].includes(project.phase);

  return (
    <div className="panel run">
      <div className="run-header">
        <h2>Exécution</h2>
        <span className={`phase phase-${project.phase}`}>
          {PHASE_LABEL[project.phase]} — itération {project.iteration}
          {project.auto_spec && loopActive ? " (boucle auto-spec)" : ""}
        </span>
        <div className="run-buttons">
          <button className="primary" disabled={!canRun || project.running} onClick={onRun}>
            {project.running ? "▶ En cours…" : "▶ Lancer le projet"}
          </button>
          {(loopActive || project.auto_spec) && (
            <button className="danger" disabled={!loopActive} onClick={onStop}>
              ⏹ Stopper la boucle
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
