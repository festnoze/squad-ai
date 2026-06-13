import { FeatureHypothesis } from "../types";

const STATUS_LABEL: Record<string, string> = {
  proposed: "proposée",
  selected: "en cours",
  done: "livrée",
  rejected: "rejetée",
};

interface Props {
  backlog: FeatureHypothesis[];
}

export function BacklogPanel({ backlog }: Props) {
  if (backlog.length === 0) return null;
  const active = backlog
    .filter((h) => h.status !== "done")
    .sort((a, b) => a.rank - b.rank);
  const shipped = backlog.filter((h) => h.status === "done");

  return (
    <div className="panel backlog">
      <h2>Backlog de l'analyste (kanban)</h2>
      <div className="hypotheses">
        {active.map((h) => (
          <div key={h.id} className={`hypothesis hyp-${h.status}`} title={h.rationale}>
            <span className="hyp-rank">#{h.rank}</span>
            <span className="hyp-title">{h.title}</span>
            <span className="hyp-scores">
              V{h.value} / C{h.complexity}
            </span>
            <span className={`badge badge-hyp-${h.status}`}>
              {STATUS_LABEL[h.status] ?? h.status}
            </span>
          </div>
        ))}
        {shipped.length > 0 && (
          <div className="hyp-shipped">
            ✅ Livrées : {shipped.map((h) => h.title).join(", ")}
          </div>
        )}
      </div>
    </div>
  );
}
