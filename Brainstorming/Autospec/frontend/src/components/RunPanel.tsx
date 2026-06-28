import { useEffect, useRef, useState } from "react";
import { LogLine, ProjectState } from "../types";
import { canResumeBuild, effectiveStatus } from "../work";
import { useI18n } from "../i18n/i18n";

interface Props {
  project: ProjectState;
  logs: LogLine[];
  onRun: (args: string) => void;
  onStop: () => void;
  onPause: () => void;
  onResume: () => void;
  onStopApp: () => void;
  onResumeBuild: () => void;
  onRetryFailed: () => void;
  onDocument: () => void;
  onExportZip: () => void;
  onGitExport: () => void;
  onCancelResume: () => void;
  onApprove: () => void;
  onReject: () => void;
  onDeploy: () => void;
}

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

export function RunPanel({
  project,
  logs,
  onRun,
  onStop,
  onPause,
  onResume,
  onStopApp,
  onResumeBuild,
  onRetryFailed,
  onDocument,
  onExportZip,
  onGitExport,
  onCancelResume,
  onApprove,
  onReject,
  onDeploy,
}: Props) {
  const { t } = useI18n();
  // Phase labels are built inside render so they re-translate on language change.
  const PHASE_LABEL: Record<string, string> = {
    idle: t("runPanel.phaseIdle"),
    spec: t("runPanel.phaseSpec"),
    analyze: t("runPanel.phaseAnalyze"),
    architect: t("runPanel.phaseArchitect"),
    plan: t("runPanel.phasePlan"),
    build: t("runPanel.phaseBuild"),
    done: t("runPanel.phaseDone"),
    stopped: t("runPanel.phaseStopped"),
    error: t("runPanel.phaseError"),
  };
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
  // Optional CLI args forwarded to the generated app on run (e.g. a subcommand
  // for a CLI app that just prints usage when launched bare).
  const [runArgs, setRunArgs] = useState("");
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
  // Phase dormante (done/stopped/error) + au moins une story à construire (statut
  // EFFECTIF). Logique partagée avec ProjectBar via work.ts pour éviter toute
  // dérive (l'oubli de `done` ici était le bug « Continuer le build »).
  const showResumeBuild = canResumeBuild(project);
  // Statut EFFECTIF par story (cf. canResumeBuild) : une US multi-stream à moitié
  // construite peut être effective failed/done/in_progress sans que son status
  // stocké le reflète. On l'aligne sur le backend (aretry_failed agit sur
  // effective_status). effectiveStatus renvoie le status brut pour une US sans tâche.
  const effStatuses = (project.stories ?? []).map((s) => effectiveStatus(s));
  // Bulk « relancer les échecs » : actif quand la pipeline est dormante et qu'au
  // moins une story est en échec.
  const failedCount = effStatuses.filter((st) => st === "failed").length;
  const canRetryFailed =
    ["done", "stopped", "error"].includes(project.phase) && failedCount > 0;

  const agentCalls = project.usage?.agent_calls ?? 0;
  const costUsd = project.usage?.cost_usd ?? 0;
  const totalTokens = (project.usage?.input_tokens ?? 0) + (project.usage?.output_tokens ?? 0);
  const budgetUsd = project.budget_usd ?? 0;
  const overBudget = budgetUsd > 0 && costUsd >= budgetUsd;

  // O2 : estimation du coût restant à partir de l'historique du projet.
  const doneCount = effStatuses.filter((st) => st === "done").length;
  const pendingCount = effStatuses.filter((st) =>
    ["todo", "red", "in_progress", "green"].includes(st),
  ).length;
  const forecastUsd =
    doneCount > 0 && costUsd > 0 ? (costUsd / doneCount) * pendingCount : 0;

  return (
    <div className={`panel run${logsExpanded ? "" : " run-collapsed"}`}>
      <div className="run-header">
        <h2>{t("runPanel.title")}</h2>
        <span className={`phase phase-${project.phase}`}>
          {PHASE_LABEL[project.phase] ?? project.phase} — {t("runPanel.iteration", { n: project.iteration })}
          {project.paused ? t("runPanel.paused") : project.auto_spec && loopActive ? t("runPanel.autoSpecLoop") : ""}
        </span>
        {project.phase === "error" && (
          <span className="run-error" title={t("runPanel.errorTitle")}>
            ⚠️ {project.error?.trim() || t("runPanel.errorNoDetail")}
          </span>
        )}
        {(project.regressions?.length ?? 0) > 0 && (
          <span className="regression-banner" title={t("runPanel.regressionTitle")}>
            {t("runPanel.regressionCount", { n: project.regressions!.length })}
          </span>
        )}
        {(project.delivery_issues?.length ?? 0) > 0 && (
          <span className="run-error" title={project.delivery_issues!.join("\n")}>
            ⛔ Livraison · {project.delivery_issues!.length}
          </span>
        )}
        {project.awaiting_approval && (
          <span className="approval-banner" title={t("runPanel.approvalTitle")}>
            {t("runPanel.approvalRequired", { phase: project.awaiting_approval })}
            <button className="small-btn approve-btn" onClick={onApprove}>
              {t("runPanel.approve")}
            </button>
            <button className="small-btn danger" onClick={onReject}>
              {t("runPanel.reject")}
            </button>
          </span>
        )}
        {(project.resume_at ?? 0) > 0 && (
          <span className="resume-banner" title={t("runPanel.resumeTitle")}>
            {t("runPanel.resumeAt")}
            {new Date((project.resume_at ?? 0) * 1000).toLocaleTimeString("fr-FR", {
              hour: "2-digit",
              minute: "2-digit",
            })}
            <button
              className="small-btn"
              onClick={onCancelResume}
              title={t("runPanel.cancelAutoResume")}
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
            · {formatTokens(totalTokens)} {t("runPanel.usageTokens")} · {agentCalls} {t("runPanel.usageCalls")}
          </span>
        )}
        {pendingCount > 0 && forecastUsd > 0 && (
          <span
            className="forecast-meter"
            title={t("runPanel.forecastTitle")}
          >
            {t("runPanel.forecast", { cost: forecastUsd.toFixed(2), n: pendingCount })}
          </span>
        )}
        <div className="run-buttons">
          {canRun && !project.running && (
            <input
              className="run-args"
              type="text"
              value={runArgs}
              onChange={(e) => setRunArgs(e.target.value)}
              placeholder={t("runPanel.argsPlaceholder")}
              title={t("runPanel.argsTitle")}
              onKeyDown={(e) => {
                if (e.key === "Enter") onRun(runArgs.trim());
              }}
            />
          )}
          <button
            className="primary"
            disabled={!canRun || project.running}
            onClick={() => onRun(runArgs.trim())}
          >
            {project.running ? t("runPanel.running") : t("runPanel.runProject")}
          </button>
          {showResumeBuild && (
            <button
              className="primary"
              onClick={onResumeBuild}
              title={t("runPanel.resumeBuildTitle")}
            >
              {t("runPanel.resumeBuild")}
            </button>
          )}
          {canRetryFailed && (
            <button
              className="action-btn"
              onClick={onRetryFailed}
              title={t("runPanel.retryFailedTitle")}
            >
              {t("runPanel.retryFailed", { n: failedCount })}
            </button>
          )}
          {project.running && (
            <button className="danger" onClick={onStopApp} title={t("runPanel.stopAppTitle")}>
              {t("runPanel.stopApp")}
            </button>
          )}
          {loopActive &&
            (project.paused ? (
              <button onClick={onResume} title={t("runPanel.resumePipelineTitle")}>
                {t("runPanel.resumePipeline")}
              </button>
            ) : (
              <button onClick={onPause} title={t("runPanel.pausePipelineTitle")}>
                {t("runPanel.pausePipeline")}
              </button>
            ))}
          {(loopActive || project.auto_spec) && (
            <button className="danger" disabled={!loopActive} onClick={onStop}>
              {t("runPanel.stop")}
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
                title={t("runPanel.deliveryTitle")}
              >
                {t("runPanel.delivery")}
              </button>
              {menuOpen && (
                <div className="run-menu" role="menu">
                  <button role="menuitem" onClick={() => { setMenuOpen(false); onDocument(); }}>
                    {t("runPanel.doc")}
                  </button>
                  <button role="menuitem" onClick={() => { setMenuOpen(false); onExportZip(); }}>
                    {t("runPanel.exportZip")}
                  </button>
                  <button role="menuitem" onClick={() => { setMenuOpen(false); onGitExport(); }}>
                    {t("runPanel.gitCommit")}
                  </button>
                  <button role="menuitem" onClick={() => { setMenuOpen(false); onDeploy(); }}>
                    {t("runPanel.deploy")}
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
          title={hasLogs ? t("runPanel.logsToggleTitle") : t("runPanel.logsEmptyTitle")}
        >
          {hasLogs ? `${logsOpen ? "▾" : "▸"} ${t("runPanel.logsCount", { n: logs.length })}` : t("runPanel.logsEmpty")}
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
