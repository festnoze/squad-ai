import { ProjectState } from "../types";

const PHASE_DOT: Record<string, string> = {
  idle: "#8a93a6",
  spec: "#ffb454",
  analyze: "#b07cff",
  plan: "#b07cff",
  build: "#4f8cff",
  done: "#3ecf8e",
  stopped: "#8a93a6",
  error: "#ff5c6c",
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
}: Props) {
  const archivedCount = projects.filter((p) => p.archived).length;
  const visible = showArchived ? projects : projects.filter((p) => !p.archived);

  return (
    <div className="project-bar">
      {visible.map((p) => (
        <div
          key={p.id}
          className={`project-chip ${p.id === selectedId ? "active" : ""} ${
            p.archived ? "archived" : ""
          }`}
          onClick={() => onSelect(p.id)}
        >
          <span className="dot" style={{ background: PHASE_DOT[p.phase] ?? "#8a93a6" }} />
          <span className="chip-name">{p.name}</span>
          {p.archived ? (
            <button
              className="chip-del chip-archive"
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
              className="chip-del chip-archive"
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
      ))}
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
