import { ProjectState } from "../types";

const PHASE_DOT: Record<string, string> = {
  idle: "#8a93a6",
  spec: "#ffb454",
  analyze: "#b07cff",
  plan: "#b07cff",
  architect: "#39c5bb",
  build: "#4f8cff",
  done: "#3ecf8e",
  stopped: "#8a93a6",
  error: "#ff5c6c",
};

/** Phases où des agents travaillent : la chip pulse et propose ⏹. */
const ACTIVE_PHASES = ["spec", "analyze", "plan", "architect", "build"];

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

/** Une story encore à construire rend le projet « relançable » (resume-build). */
function hasPendingStories(p: ProjectState): boolean {
  return (p.stories ?? []).some((s) => s.status === "todo" || s.status === "red");
}

function progress(p: ProjectState): { done: number; total: number } | null {
  const stories = p.stories ?? [];
  if (stories.length === 0) return null;
  return {
    done: stories.filter((s) => s.status === "done").length,
    total: stories.length,
  };
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
  const archivedCount = projects.filter((p) => p.archived).length;
  const visible = showArchived ? projects : projects.filter((p) => !p.archived);

  return (
    <div className="project-bar">
      {visible.map((p) => {
        const active = ACTIVE_PHASES.includes(p.phase);
        const working = active && !p.paused;
        const canPlay =
          (active && p.paused) ||
          (["stopped", "error", "done"].includes(p.phase) && hasPendingStories(p));
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
              title={p.paused ? `${p.phase} (en pause)` : p.phase}
            />
            <span className="chip-name">{p.name}</span>
            {prog && (
              <span
                className="chip-progress"
                title={`${prog.done} story(ies) terminée(s) sur ${prog.total}`}
              >
                {prog.done}/{prog.total}
              </span>
            )}
            {working && (
              <button
                className="chip-play"
                title="Stopper la pipeline de ce projet"
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
                    ? "Reprendre la pipeline"
                    : "Reprendre le build des stories restantes"
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
                title="Désarchiver le projet"
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
                title="Archiver le projet"
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
              title="Supprimer le projet"
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
      <button className="project-new" onClick={onNew}>
        ＋ Nouveau
      </button>
      {archivedCount > 0 && (
        <button
          className={`archived-toggle ${showArchived ? "active" : ""}`}
          onClick={onToggleArchived}
          title={showArchived ? "Masquer les projets archivés" : "Afficher les projets archivés"}
        >
          📦 Archivés ({archivedCount})
        </button>
      )}
    </div>
  );
}
