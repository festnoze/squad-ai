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
}

export function ProjectBar({ projects, selectedId, onSelect, onNew, onDelete }: Props) {
  return (
    <div className="project-bar">
      {projects.map((p) => (
        <div
          key={p.id}
          className={`project-chip ${p.id === selectedId ? "active" : ""}`}
          onClick={() => onSelect(p.id)}
        >
          <span className="dot" style={{ background: PHASE_DOT[p.phase] ?? "#8a93a6" }} />
          <span className="chip-name">{p.name}</span>
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
    </div>
  );
}
