import { useEffect, useState } from "react";
import { fetchWalkForward } from "../api";
import type { LeaderRow, WalkForward } from "../types";
import { agentColor, brierStr, skillStr } from "../util";

// The honesty check. Pick the best agent on the earlier half of history, then see whether it still leads
// on the later half it never saw. When the two winners differ, the "edge" on the past was partly luck.
export function WalkForwardView() {
  const [wf, setWf] = useState<WalkForward | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetchWalkForward().then(setWf).catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="err">Failed to load: {err}</div>;
  if (!wf) return <div className="loading">Splitting history…</div>;

  return (
    <div className="wf-view">
      <div className="board-lead">
        <h2>Does the winner generalise?</h2>
        <p>
          Trained on the {wf.train_ids.length} earliest markets, tested on the {wf.test_ids.length} later
          ones. If the agent that won the past does not win the future, its edge was partly noise. This is
          the difference between a real strategy and a story fit to old data.
        </p>
      </div>

      <div className={`verdict ${wf.generalised ? "ok" : "warn"}`}>
        {wf.generalised ? (
          <>
            <b>{wf.train_winner}</b> won the past and held up on the future. The edge generalised.
          </>
        ) : (
          <>
            <b>{wf.train_winner}</b> won the past, but <b>{wf.test_winner}</b> won the held-out future.
            The train edge did not carry over: overfitting risk.
          </>
        )}
      </div>

      <div className="wf-cols">
        <WfBoard title="TRAIN (the past)" rows={wf.train_board} winner={wf.train_winner} />
        <WfBoard title="TEST (held-out future)" rows={wf.test_board} winner={wf.test_winner} />
      </div>
    </div>
  );
}

function WfBoard({ title, rows, winner }: { title: string; rows: LeaderRow[]; winner: string }) {
  return (
    <div className="wf-board">
      <h3>{title}</h3>
      <table className="lead-table small">
        <thead>
          <tr>
            <th>#</th>
            <th>agent</th>
            <th>Brier</th>
            <th>skill</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.agent_id} className={r.agent_id === winner ? "winner-row" : ""}>
              <td className="num">{i + 1}</td>
              <td>
                <span className="swatch" style={{ background: agentColor(r.agent_id) }} /> {r.agent_id}
              </td>
              <td className="num">{brierStr(r.mean_brier_micro)}</td>
              <td className={`num ${r.skill_vs_market_micro >= 0 ? "pos" : "neg"}`}>
                {skillStr(r.skill_vs_market_micro)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
