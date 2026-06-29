import { ProjectState } from "../types";
import { canResumeBuild } from "../work";
import { useI18n } from "../i18n/i18n";

const PHASE_DOT: Record<string, string> = {
  idle: "#8a93a6",
  spec: "#ffb454",
  analyze: "#b07cff",
  plan: "#b07cff",
  architect: "#39c5bb",
  build: "#4f8cff",
  done: "#3ecf8e",
  stopped: "#8a93a6",
  needs_attention: "#ffb454",
  error: "#ff5c6c",
};

/** Phases où des agents travaillent : la chip pulse et propose ⏹. */
const ACTIVE_PHASES = ["spec", "analyze", "plan", "architect", "build"];

/** Pastille de statut (texte) pour les <option> du sélecteur de projet. */
const PHASE_BADGE: Record<string, string> = {
  idle: "⚪",
  spec: "🟠",
  analyze: "🟣",
  plan: "🟣",
  architect: "🟢",
  build: "🔵",
  done: "🟢",
  stopped: "⚪",
  needs_attention: "🟠",
  error: "🔴",
};

interface Props {
  projects: ProjectState[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (project: ProjectState) => void;
  showArchived: boolean;
  onToggleArchived: () => void;
  onArchive: (project: ProjectState) => void;
  onUnarchive: (project: ProjectState) => void;
  onPlay: (project: ProjectState) => void;
  onStop: (project: ProjectState) => void;
}

function progress(p: ProjectState): { done: number; total: number } | null {
  const stories = p.stories ?? [];
  if (stories.length === 0) return null;
  return {
    done: stories.filter((s) => s.status === "done").length,
    total: stories.length,
  };
}

/** Ordre d'affichage (UI3) : en cours → en pause → dormant → terminé. */
function statusRank(p: ProjectState): number {
  if (ACTIVE_PHASES.includes(p.phase)) return p.paused ? 1 : 0;
  if (["stopped", "needs_attention", "error"].includes(p.phase)) return 2;
  if (p.phase === "done") return 3;
  return 4;
}

export function ProjectBar({
  projects,
  selectedId,
  onSelect,
  onNew,
  onDelete,
  showArchived,
  onToggleArchived,
  onArchive,
  onUnarchive,
  onPlay,
  onStop,
}: Props) {
  const { t } = useI18n();

  /** Libellé d'une option du sélecteur : « 🔵 Nom · 2/3 · build ». */
  const optionLabel = (p: ProjectState): string => {
    const badge = p.paused ? "⏸" : PHASE_BADGE[p.phase] ?? "⚪";
    const prog = progress(p);
    const parts = [`${badge} ${p.name}`];
    if (prog) parts.push(`${prog.done}/${prog.total}`);
    parts.push(p.paused ? t("projectBar.phasePaused", { phase: p.phase }) : p.phase);
    if (p.archived) parts.push(t("projectBar.archived"));
    return parts.join(" · ");
  };

  const archivedCount = projects.filter((p) => p.archived).length;
  const visible = showArchived ? projects : projects.filter((p) => !p.archived);

  const selected = projects.find((p) => p.id === selectedId) ?? null;
  const sorted = [...visible].sort((a, b) => statusRank(a) - statusRank(b));
  // Le sélecteur liste tout (projet courant inclus même archivé/masqué).
  const selectable =
    selected && !sorted.some((p) => p.id === selected.id)
      ? [selected, ...sorted]
      : sorted;
  // UI3 : les chips se limitent aux projets qui travaillent (ou en pause) + le
  // projet courant ; le reste se commute via le sélecteur 🗂 (fini l'overflow).
  const chipProjects = sorted.filter(
    (p) => ACTIVE_PHASES.includes(p.phase) || p.id === selectedId,
  );
  const hiddenFromChips = visible.length - chipProjects.length;

  return (
    <div className="project-bar">
      {selectable.length > 0 && (
        <label className="project-select" title={t("projectBar.selectActiveProject")}>
          <span className="project-select-icon" aria-hidden="true">
            🗂
          </span>
          <select
            aria-label={t("projectBar.selectActiveProject")}
            value={selectedId ?? ""}
            onChange={(e) => onSelect(e.target.value)}
          >
            <option value="" disabled hidden>
              {t("projectBar.chooseProject", { count: selectable.length })}
            </option>
            {selectable.map((p) => (
              <option key={p.id} value={p.id}>
                {optionLabel(p)}
              </option>
            ))}
          </select>
        </label>
      )}
      {chipProjects.map((p) => {
        const active = ACTIVE_PHASES.includes(p.phase);
        const working = active && !p.paused;
        // ▶ = reprendre la pipeline en pause, ou relancer le build des stories
        // restantes d'un projet dormant (logique partagée via work.ts).
        const canPlay = (active && p.paused) || canResumeBuild(p);
        const prog = progress(p);
        return (
          <div
            key={p.id}
            className={`project-chip ${p.id === selectedId ? "active" : ""} ${
              p.archived ? "archived" : ""
            }`}
            onClick={() => onSelect(p.id)}
          >
            <span
              className={`dot ${working ? "pulse" : ""}`}
              style={{ background: PHASE_DOT[p.phase] ?? "#8a93a6" }}
              title={p.paused ? t("projectBar.phasePausedDot", { phase: p.phase }) : p.phase}
            />
            <span className="chip-name">{p.name}</span>
            {prog && (
              <span
                className="chip-progress"
                title={t("projectBar.progressTitle", { done: prog.done, total: prog.total })}
              >
                {prog.done}/{prog.total}
              </span>
            )}
            {working && (
              <button
                className="chip-play"
                title={t("projectBar.stopPipeline")}
                onClick={(e) => {
                  e.stopPropagation();
                  onStop(p);
                }}
              >
                ⏹
              </button>
            )}
            {canPlay && (
              <button
                className="chip-play"
                title={
                  p.paused
                    ? t("projectBar.resumePipeline")
                    : t("projectBar.resumeBuild")
                }
                onClick={(e) => {
                  e.stopPropagation();
                  onPlay(p);
                }}
              >
                ▶
              </button>
            )}
            {p.archived ? (
              <button
                className="chip-archive"
                title={t("projectBar.unarchiveProject")}
                onClick={(e) => {
                  e.stopPropagation();
                  onUnarchive(p);
                }}
              >
                ↩
              </button>
            ) : (
              <button
                className="chip-archive"
                title={t("projectBar.archiveProject")}
                onClick={(e) => {
                  e.stopPropagation();
                  onArchive(p);
                }}
              >
                📦
              </button>
            )}
            <button
              className="chip-del"
              title={t("projectBar.deleteProject")}
              onClick={(e) => {
                e.stopPropagation();
                onDelete(p);
              }}
            >
              ✕
            </button>
          </div>
        );
      })}
      {hiddenFromChips > 0 && (
        <span
          className="chips-hint"
          title={t("projectBar.inactiveHint")}
        >
          {t("projectBar.hiddenCount", { count: hiddenFromChips })}
        </span>
      )}
      <button className="project-new" onClick={onNew}>
        {t("projectBar.new")}
      </button>
      {archivedCount > 0 && (
        <button
          className={`archived-toggle ${showArchived ? "active" : ""}`}
          onClick={onToggleArchived}
          title={showArchived ? t("projectBar.hideArchived") : t("projectBar.showArchived")}
        >
          {t("projectBar.archivedToggle", { count: archivedCount })}
        </button>
      )}
    </div>
  );
}
