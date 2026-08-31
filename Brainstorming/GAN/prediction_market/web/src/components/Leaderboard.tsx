import { useEffect, useState } from "react";
import { fetchTournament } from "../api";
import type { Tournament } from "../types";
import { agentColor, brierStr, dollars, skillStr } from "../util";

// The headline answer: across every market, which agent forecasts best and which actually beats the
// market. The skill column (market Brier minus agent Brier) is the honest measure; a bar makes the sign
// and size read at a glance. market_follower sits at exactly zero by construction.
export function Leaderboard() {
  const [t, setT] = useState<Tournament | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetchTournament().then(setT).catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="err">Failed to load: {err}</div>;
  if (!t) return <div className="loading">Running the tournament…</div>;

  const maxSkill = Math.max(...t.board.map((r) => Math.abs(r.skill_vs_market_micro)), 1);
  const best = t.board[0];

  return (
    <div className="board-view">
      <div className="board-lead">
        <h2>Who beats the market?</h2>
        <p>
          Every agent forecast every one of {best.markets} real resolved markets. Lower Brier is a
          sharper forecaster; <b>skill</b> is the market's own Brier minus the agent's, so positive means
          it beat the crowd. Beating the market is meant to be hard: that is the whole point.
        </p>
      </div>
      <table className="lead-table">
        <thead>
          <tr>
            <th>#</th>
            <th>agent</th>
            <th>mean Brier</th>
            <th>beat market</th>
            <th>total PnL</th>
            <th>skill vs market</th>
          </tr>
        </thead>
        <tbody>
          {t.board.map((r, i) => (
            <tr key={r.agent_id} className={r.agent_id === "market_follower" ? "baseline-row" : ""}>
              <td className="num">{i + 1}</td>
              <td>
                <span className="swatch" style={{ background: agentColor(r.agent_id) }} /> {r.agent_id}
                {r.agent_id === "market_follower" && <span className="base">baseline</span>}
              </td>
              <td className="num">{brierStr(r.mean_brier_micro)}</td>
              <td className="num">{r.beat_market_pct}%</td>
              <td className={`num ${r.total_pnl_cents >= 0 ? "pos" : "neg"}`}>{dollars(r.total_pnl_cents)}</td>
              <td>
                <div className="skill-cell">
                  <span className={`num ${r.skill_vs_market_micro >= 0 ? "pos" : "neg"}`}>
                    {skillStr(r.skill_vs_market_micro)}
                  </span>
                  <span className="skill-bar">
                    <i
                      className={r.skill_vs_market_micro >= 0 ? "pos" : "neg"}
                      style={{
                        width: `${(Math.abs(r.skill_vs_market_micro) / maxSkill) * 50}%`,
                        marginLeft: r.skill_vs_market_micro >= 0 ? "50%" : undefined,
                        marginRight: r.skill_vs_market_micro < 0 ? "50%" : undefined,
                      }}
                    />
                  </span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
