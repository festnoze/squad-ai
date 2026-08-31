import type { Backtest } from "../types";
import { agentColor, pct } from "../util";

// The hero chart. The market's YES price is the bold white line; each selected agent's stated
// probability is a thin coloured line tracking it. The vertical cursor marks the current tick. Once you
// reach the end, the resolution is revealed as a green (YES) or red (NO) band, so you can see which
// lines were converging on the truth and which were fighting it.
export function PriceChart({
  bt,
  tick,
  selected,
  revealed,
}: {
  bt: Backtest;
  tick: number;
  selected: Set<string>;
  revealed: boolean;
}) {
  const W = 900;
  const H = 340;
  const padL = 40;
  const padR = 16;
  const padT = 16;
  const padB = 34;
  const n = bt.ticks.length;
  const x = (i: number) => padL + (i / Math.max(1, n - 1)) * (W - padL - padR);
  const y = (cents: number) => padT + (1 - cents / 100) * (H - padT - padB);

  const marketPath = bt.ticks
    .slice(0, tick + 1)
    .map((r, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(r.price).toFixed(1)}`)
    .join(" ");

  const agentPath = (id: string) =>
    bt.ticks
      .slice(0, tick + 1)
      .map((r, i) => {
        const p = r.agents[id]?.prob_ppm ?? 500_000;
        return `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(pct(p)).toFixed(1)}`;
      })
      .join(" ");

  const yesBand = bt.market.resolution === 1;

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Market price and agent forecasts over time">
        {/* resolution line, revealed at the end */}
        {revealed && (
          <g>
            <line
              x1={padL}
              x2={W - padR}
              y1={y(yesBand ? 100 : 0)}
              y2={y(yesBand ? 100 : 0)}
              className={yesBand ? "reso-line yes" : "reso-line no"}
            />
            <text x={W - padR} y={y(yesBand ? 100 : 0) + (yesBand ? 14 : -6)} textAnchor="end" className={`reso-label ${yesBand ? "yes" : "no"}`}>
              resolved {yesBand ? "YES (100)" : "NO (0)"}
            </text>
          </g>
        )}

        {/* gridlines */}
        {[0, 25, 50, 75, 100].map((g) => (
          <g key={g}>
            <line x1={padL} x2={W - padR} y1={y(g)} y2={y(g)} className="grid" />
            <text x={padL - 6} y={y(g) + 3} textAnchor="end" className="axis">
              {g}
            </text>
          </g>
        ))}

        {/* agent forecast lines */}
        {bt.agent_ids
          .filter((id) => selected.has(id))
          .map((id) => (
            <path key={id} d={agentPath(id)} fill="none" stroke={agentColor(id)} strokeWidth={1.6} opacity={0.85} />
          ))}

        {/* the market price, bold */}
        <path d={marketPath} fill="none" className="market-line" strokeWidth={2.6} />

        {/* current-tick cursor */}
        <line x1={x(tick)} x2={x(tick)} y1={padT} y2={H - padB} className="cursor" />
        <circle cx={x(tick)} cy={y(bt.ticks[tick].price)} r={4} className="market-dot" />

        <text x={padL} y={H - 8} className="axis">
          {bt.ticks[0].t}
        </text>
        <text x={W - padR} y={H - 8} textAnchor="end" className="axis">
          {bt.ticks[bt.ticks.length - 1].t}
        </text>
      </svg>
    </div>
  );
}
