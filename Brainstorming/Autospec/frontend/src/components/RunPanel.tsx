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
  onDocument: () => void;
  onExportZip: () => void;
  onGitExport: () => void;
  onCancelResume: () => void;
}

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
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

export function RunPanel({
  project,
  logs,
  onRun,
  onStop,
  onPause,
  onResume,
  onStopApp,
  onResumeBuild,
  onDocument,
  onExportZip,
  onGitExport,
  onCancelResume,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs.length]);

  const canRun = !["spec", "plan", "analyze", "architect", "build", "idle"].includes(
    project.phase,
  );
  const loopActive = !["done", "stopped", "error"].includes(project.phase);
  const canResumeBuild =
    ["stopped", "error"].includes(project.phase) &&
    (project.stories ?? []).some((s) => s.status === "todo" || s.status === "red");

  const agentCalls = project.usage?.agent_calls ?? 0;
  const costUsd = project.usage?.cost_usd ?? 0;
  const totalTokens = (project.usage?.input_tokens ?? 0) + (project.usage?.output_tokens ?? 0);
  const budgetUsd = project.budget_usd ?? 0;
  const overBudget = budgetUsd > 0 && costUsd >= budgetUsd;

  return (
    <div className="panel run">
      <div className="run-header">
        <h2>Exécution</h2>
        <span className={`phase phase-${project.phase}`}>
          {PHASE_LABEL[project.phase] ?? project.phase} — itération {project.iteration}
          {project.paused ? " ⏸ en pause" : project.auto_spec && loopActive ? " (boucle auto-spec)" : ""}
        </span>
        {(project.resume_at ?? 0) > 0 && (
          <span className="resume-banner" title="Fenêtre d'usage Claude épuisée : le travail reprendra automatiquement">
            ⏰ Reprise auto à{" "}
            {new Date((project.resume_at ?? 0) * 1000).toLocaleTimeString("fr-FR", {
              hour: "2-digit",
              minute: "2-digit",
            })}
            <button
              className="small-btn"
              onClick={onCancelResume}
              title="Annuler la reprise automatique"
            >
              ✕
            </button>
          </span>
        )}
        {agentCalls > 0 && (
          <span className={`usage-meter${overBudget ? " over-budget" : ""}`}>
            {budgetUsd > 0
              ? `💸 $${costUsd.toFixed(4)} / $${budgetUsd.toFixed(2)}`
              : `💸 $${costUsd.toFixed(4)}`}{" "}
            · {formatTokens(totalTokens)} tokens · {agentCalls} appels
          </span>
        )}
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
          {canRun && (
            <>
              <button onClick={onDocument} title="Générer la doc du projet (README via tech-writer)">
                📘 Doc
              </button>
              <button onClick={onExportZip} title="Télécharger le code généré (zip)">
                ⬇ Zip
              </button>
              <button onClick={onGitExport} title="Commit git propre du workspace généré">
                🔀 Commit
              </button>
            </>
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
