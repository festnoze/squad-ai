import type { ProjectSummary } from "../api";
import { formatCost, formatDateTime } from "../format";
import { routeHash } from "../route";
import { PhaseBadge } from "./PhaseBadge";

export function ProjectList({ projects }: { projects: ProjectSummary[] }) {
  if (projects.length === 0) {
    return <p className="empty">Aucun projet pour l'instant. Créez-en un ci-dessous.</p>;
  }
  return (
    <div className="table-wrap">
      <table className="projects">
        <caption className="visually-hidden">Projets, du plus récent au plus ancien</caption>
        <thead>
          <tr>
            <th scope="col">Nom</th>
            <th scope="col">Profil</th>
            <th scope="col">Phase</th>
            <th scope="col">Progression</th>
            <th scope="col" className="num">Coût</th>
            <th scope="col">Mis à jour</th>
          </tr>
        </thead>
        <tbody>
          {projects.map((project) => (
            <tr key={project.id}>
              <th scope="row">
                <a href={routeHash({ name: "project", id: project.id })}>{project.name}</a>
                {project.error && <span className="row-error" title={project.error}> (erreur)</span>}
              </th>
              <td>{project.profile ?? "-"}</td>
              <td>
                <PhaseBadge phase={project.phase} running={project.running} />
              </td>
              <td>
                <Progress done={project.stories_done} total={project.stories_total} />
              </td>
              <td className="num">{formatCost(project.cost_usd)}</td>
              <td>{formatDateTime(project.updated_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Progress({ done, total }: { done: number; total: number }) {
  return (
    <span className="progress">
      <progress value={done} max={Math.max(total, 1)} aria-label={`${done} stories terminées sur ${total}`} />
      <span>
        {done}/{total}
      </span>
    </span>
  );
}
