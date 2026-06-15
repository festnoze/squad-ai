import { useEffect, useRef, useState } from "react";
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
  onApprove: () => void;
  onReject: () => void;
  onRollback: () => void;
  onDeploy: () => void;
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
  onApprove,
  onReject,
  onRollback,
  onDeploy,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  // UI7: post-build delivery/export actions live in an overflow menu so the
  // primary controls (Lancer/Pause/Stop) stay prominent.
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menuOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [menuOpen]);
  // UI4: the log box only takes space when there are logs to show (and the user
  // can collapse it). An empty project no longer reserves a big black void.
  const [logsOpen, setLogsOpen] = useState(true);
  const hasLogs = logs.length > 0;
  const logsExpanded = logsOpen && hasLogs;
  useEffect(() => {
    if (logsExpanded) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs.length, logsExpanded]);

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

  // O2 : estimation du coût restant à partir de l'historique du projet.
  const doneCount = (project.stories ?? []).filter((s) => s.status === "done").length;
  const pendingCount = (project.stories ?? []).filter((s) =>
    ["todo", "red", "in_progress", "green"].includes(s.status),
  ).length;
  const forecastUsd =
    doneCount > 0 && costUsd > 0 ? (costUsd / doneCount) * pendingCount : 0;

  return (
    <div className={`panel run${logsExpanded ? "" : " run-collapsed"}`}>
      <div className="run-header">
        <h2>Exécution</h2>
        <span className={`phase phase-${project.phase}`}>
          {PHASE_LABEL[project.phase] ?? project.phase} — itération {project.iteration}
          {project.paused ? " ⏸ en pause" : project.auto_spec && loopActive ? " (boucle auto-spec)" : ""}
        </span>
        {project.phase === "error" && (
          <span className="run-error" title="Détail de l'erreur de la pipeline">
            ⚠️ {project.error?.trim() || "Erreur sans détail (voir les logs / le chat)."}
          </span>
        )}
        {(project.regressions?.length ?? 0) > 0 && (
          <span className="regression-banner" title="Des tests précédemment verts ont été cassés">
            ⚠️ {project.regressions!.length} régression(s)
          </span>
        )}
        {project.awaiting_approval && (
          <span className="approval-banner" title="Validation requise avant le build">
            ⏸ Validation requise ({project.awaiting_approval})
            <button className="small-btn approve-btn" onClick={onApprove}>
              ✅ Approuver
            </button>
            <button className="small-btn danger" onClick={onReject}>
              ✋ Rejeter
            </button>
          </span>
        )}
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
        {pendingCount > 0 && forecastUsd > 0 && (
          <span
            className="forecast-meter"
            title="Estimation du coût restant (historique coût/story du projet)"
          >
            📈 ~${forecastUsd.toFixed(2)} / {pendingCount} story(ies)
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
            <div className="run-menu-wrap" ref={menuRef}>
              <button
                type="button"
                className="ghost"
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen((o) => !o)}
                title="Livraison & export du produit généré"
              >
                ⋯ Livraison
              </button>
              {menuOpen && (
                <div className="run-menu" role="menu">
                  <button role="menuitem" onClick={() => { setMenuOpen(false); onDocument(); }}>
                    📘 Doc (README)
                  </button>
                  <button role="menuitem" onClick={() => { setMenuOpen(false); onExportZip(); }}>
                    ⬇ Exporter en zip
                  </button>
                  <button role="menuitem" onClick={() => { setMenuOpen(false); onGitExport(); }}>
                    🔀 Commit git
                  </button>
                  <button role="menuitem" onClick={() => { setMenuOpen(false); onRollback(); }}>
                    ⏪ Rollback itération
                  </button>
                  <button role="menuitem" onClick={() => { setMenuOpen(false); onDeploy(); }}>
                    🚀 Déploiement
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      <div className="logs-bar">
        <button
          type="button"
          className="logs-toggle"
          onClick={() => setLogsOpen((o) => !o)}
          disabled={!hasLogs}
          title={hasLogs ? "Afficher / masquer les logs" : "Les logs apparaîtront ici pendant l'exécution"}
        >
          {hasLogs ? `${logsOpen ? "▾" : "▸"} Logs (${logs.length})` : "Logs — aucun pour l'instant"}
        </button>
      </div>
      {logsExpanded && (
        <div className="logs">
          {logs.map((l, i) => (
            <div key={i} className="log-line">
              <span className="log-source">[{l.source}]</span> {l.line}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}
