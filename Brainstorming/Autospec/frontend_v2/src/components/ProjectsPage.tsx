import { useCallback, useEffect, useState } from "react";
import { listProjects, type ProjectSummary } from "../api";
import { CreateProjectForm } from "./CreateProjectForm";
import { ProjectList } from "./ProjectList";

export const LIST_REFRESH_MS = 5000;

export function ProjectsPage({
  onCreated,
  refreshMs = LIST_REFRESH_MS,
}: {
  onCreated: (project: ProjectSummary) => void;
  refreshMs?: number;
}) {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setProjects(await listProjects());
      setError("");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), refreshMs);
    return () => clearInterval(timer);
  }, [load, refreshMs]);

  return (
    <>
      <section className="card" aria-labelledby="projects-title">
        <div className="section-head">
          <h1 id="projects-title">Projets</h1>
          <button type="button" onClick={() => void load()}>
            Actualiser
          </button>
        </div>
        {error && (
          <p className="alert" role="alert">
            Impossible de charger les projets : {error}
          </p>
        )}
        {projects === null && !error && <p className="muted">Chargement...</p>}
        {projects !== null && <ProjectList projects={projects} />}
      </section>
      <CreateProjectForm onCreated={onCreated} />
    </>
  );
}
