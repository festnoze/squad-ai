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

/** Libellé d'une option du sélecteur : « 🔵 Nom · 2/3 · build ». */
function optionLabel(p: ProjectState): string {
  const badge = p.paused ? "⏸" : PHASE_BADGE[p.phase] ?? "⚪";
  const prog = progress(p);
  const parts = [`${badge} ${p.name}`];
  if (prog) parts.push(`${prog.done}/${prog.total}`);
  parts.push(p.paused ? `${p.phase} (pause)` : p.phase);
  if (p.archived) parts.push("archivé");
  return parts.join(" · ");
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

  const selected = projects.find((p) => p.id === selectedId) ?? null;
  // Le projet courant figure toujours dans le sélecteur, même s'il est archivé
  // et que les archivés sont masqués.
  const selectable =
    selected && !visible.some((p) => p.id === selected.id)
      ? [selected, ...visible]
      : visible;

  return (
    <div className="project-bar">
      {selectable.length > 0 && (
        <label className="project-select" title="Sélectionner le projet actif">
          <span className="project-select-icon" aria-hidden="true">
            🗂
          </span>
          <select
            aria-label="Sélectionner le projet actif"
            value={selectedId ?? ""}
            onChange={(e) => onSelect(e.target.value)}
          >
            <option value="" disabled hidden>
              — Choisir un projet ({selectable.length}) —
            </option>
            {selectable.map((p) => (
              <option key={p.id} value={p.id}>
                {optionLabel(p)}
              </option>
            ))}
          </select>
        </label>
      )}
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
