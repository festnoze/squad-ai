import { Fragment, useState } from "react";
import type { Story } from "../api";
import { STATUS_LABELS } from "../format";

export function StoriesTable({
  stories,
  selectedDiff,
  onShowDiff,
}: {
  stories: Story[];
  selectedDiff?: string | null;
  onShowDiff: (storyId: string) => void;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  if (stories.length === 0) {
    return <p className="empty">Aucune story pour l'instant (le plan n'est pas encore établi).</p>;
  }

  const toggle = (id: string) =>
    setExpanded((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className="table-wrap">
      <table className="stories">
        <caption className="visually-hidden">Stories du projet</caption>
        <thead>
          <tr>
            <th scope="col">Id</th>
            <th scope="col">Titre</th>
            <th scope="col">Statut</th>
            <th scope="col" className="num">Tentatives</th>
            <th scope="col">Critères</th>
            <th scope="col">Diff</th>
          </tr>
        </thead>
        <tbody>
          {stories.map((story) => {
            const open = expanded.has(story.id);
            const detailId = `story-detail-${story.id}`;
            return (
              <Fragment key={story.id}>
                <tr className={open ? "open" : undefined}>
                  <th scope="row" className="mono">
                    {story.id}
                  </th>
                  <td>{story.title}</td>
                  <td>
                    <span className={`badge status-${story.status}`}>{STATUS_LABELS[story.status] ?? story.status}</span>
                  </td>
                  <td className="num">{story.attempts}</td>
                  <td>
                    <button
                      type="button"
                      className="link"
                      aria-expanded={open}
                      aria-controls={detailId}
                      aria-label={`${criteriaLabel(story.criteria.length)} de ${story.id}`}
                      onClick={() => toggle(story.id)}
                    >
                      <span aria-hidden="true">{open ? "▾ " : "▸ "}</span>
                      {criteriaLabel(story.criteria.length)}
                    </button>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="link"
                      aria-pressed={selectedDiff === story.id}
                      aria-label={`Voir le diff de ${story.id}`}
                      onClick={() => onShowDiff(story.id)}
                    >
                      Voir le diff
                    </button>
                  </td>
                </tr>
                {open && (
                  <tr className="story-detail" id={detailId}>
                    <td colSpan={6}>
                      <StoryCriteria story={story} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const criteriaLabel = (count: number) => `${count} critère${count > 1 ? "s" : ""}`;

function StoryCriteria({ story }: { story: Story }) {
  // The QA may map one criterion in several entries: show all their nodeids.
  const nodeids = (acId: string) =>
    story.acceptance_tests.filter((test) => test.ac_id === acId).flatMap((test) => test.nodeids);
  return (
    <div className="criteria">
      {story.description && <p>{story.description}</p>}
      <ul aria-label={`Critères de ${story.id}`}>
        {story.criteria.map((criterion) => {
          const ids = nodeids(criterion.id);
          return (
            <li key={criterion.id}>
              <span className="mono ac-id">{criterion.id}</span> {criterion.text}
              {ids.length > 0 ? (
                <ul className="nodeids" aria-label={`Tests d'acceptance de ${criterion.id}`}>
                  {ids.map((nodeid) => (
                    <li key={nodeid}>
                      <code>{nodeid}</code>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted small">Pas encore de test d'acceptance.</p>
              )}
            </li>
          );
        })}
      </ul>
      {story.depends_on.length > 0 && <p className="small">Dépend de : {story.depends_on.join(", ")}</p>}
      {story.last_error && (
        <div className="story-error">
          <h4>Dernière erreur</h4>
          <pre>{story.last_error}</pre>
        </div>
      )}
    </div>
  );
}
