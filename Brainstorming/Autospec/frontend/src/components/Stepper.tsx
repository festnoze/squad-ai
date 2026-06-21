import { BuildStage } from "../types";
import {
  elapsedLabel,
  ItemView,
  isStageActive,
  isStageDone,
  STAGE_ORDER,
} from "../work";

/** Short label shown under each stepper cell. */
const STAGE_LABEL: Record<BuildStage, string> = {
  queued: "File",
  analyzing: "Analyse",
  contracts: "Contrats",
  implementing: "Code",
  verifying: "Vérif",
  merge_wait: "Attente merge",
  merging: "Merge",
  done: "Fini",
  failed: "Échec",
};

/** Human label for an auto-repair recovery kind. */
const RECOVERY_LABEL: Record<string, string> = {
  refining: "affinage",
  critic_restored: "critique restaurée",
  regression_rerun: "rejeu régression",
  mutation_rerun: "rejeu mutation",
  retry: "nouvelle tentative",
};

/** A tick is considered "stale" (greyed-out) once older than this (ms). */
export const STALE_MS = 25_000;

/**
 * B-UX: horizontal stage stepper for ONE work item. Shows each BUILD stage as a
 * cell (done / active / failed / pending), the elapsed time on the active stage,
 * an auto-repair sub-line ("affinage 2/3") when `view.recovery.kind` is set, and
 * greys itself out ("stale") when the heartbeat `tickTs` is older than STALE_MS.
 *
 * Accessible names / test ids the e2e stage can target:
 *  - container: role="group", aria-label={`Étapes ${view.id}`}, data-testid={`stepper-${view.id}`}
 *  - each cell: data-testid={`stage-${view.id}-${stage}`}, data-state="done|active|failed|pending"
 *  - recovery sub-line: data-testid={`recovery-${view.id}`}
 */
export function Stepper({
  view,
  now,
  tickTs,
}: {
  view: ItemView;
  /** epoch ms "now" used for elapsed + staleness. */
  now: number;
  /** epoch ms of the heartbeat this view came from (0/undefined = persisted). */
  tickTs?: number;
}) {
  const stale =
    view.fromTick && !!tickTs && now - tickTs > STALE_MS;
  const failed = view.status === "failed" || view.stage === "failed";
  const elapsed = elapsedLabel(view.stageStartedAt, now);
  const rec = view.recovery;
  const recLabel = rec && rec.kind ? RECOVERY_LABEL[rec.kind] ?? rec.kind : "";

  return (
    <div
      className={`stepper${stale ? " stepper-stale" : ""}`}
      role="group"
      aria-label={`Étapes ${view.id}`}
      data-testid={`stepper-${view.id}`}
      data-stale={stale ? "true" : "false"}
    >
      <ol className="stepper-track">
        {STAGE_ORDER.map((cell) => {
          const isTerminalFail = failed && cell === "done";
          const cellLabel = isTerminalFail ? STAGE_LABEL.failed : STAGE_LABEL[cell];
          const state = isTerminalFail
            ? "failed"
            : isStageActive(cell, view.stage)
              ? "active"
              : isStageDone(cell, view.status === "done" ? "done" : view.stage)
                ? "done"
                : "pending";
          const active = state === "active";
          return (
            <li
              key={cell}
              className={`stepper-cell stepper-${state}`}
              data-testid={`stage-${view.id}-${cell}`}
              data-state={state}
              aria-current={active ? "step" : undefined}
              title={cellLabel}
            >
              <span className="stepper-dot" aria-hidden="true" />
              <span className="stepper-cell-label">{cellLabel}</span>
              {active && elapsed && (
                <span className="stepper-elapsed">{elapsed}</span>
              )}
            </li>
          );
        })}
      </ol>
      {recLabel && (
        <div className="stepper-recovery" data-testid={`recovery-${view.id}`}>
          🔧 {recLabel}
          {rec.max_attempts > 0 ? ` ${rec.attempt}/${rec.max_attempts}` : ""}
        </div>
      )}
    </div>
  );
}
