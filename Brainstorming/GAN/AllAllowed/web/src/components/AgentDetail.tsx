import { badgeFromFlags } from "../replay";
import { buildDossier, PERMISSION_SENTENCES } from "../dossier";
import type { Family, Replay } from "../types";

// A right-side drawer opened by clicking an agent. It shows the agent's briefing (task, the permission
// sentence it was framed with, and the nature we infer from its behaviour), a credit sparkline, and its
// full move log: every tool it called, the exact input it fed that tool, and the consequences that
// followed. This is the per-agent "inputs and outputs" view.
export function AgentDetail({
  replay,
  agentId,
  currentTick,
  onClose,
}: {
  replay: Replay;
  agentId: string;
  currentTick: number;
  onClose: () => void;
}) {
  const d = buildDossier(replay.events, agentId, replay.permission);
  const badge = badgeFromFlags(d.flags);
  const sentence = PERMISSION_SENTENCES[d.permission] ?? PERMISSION_SENTENCES.silent;

  return (
    <aside className="drawer" role="dialog" aria-label={`Agent ${agentId} detail`}>
      <header className="drawer-head">
        <div>
          <div className="drawer-title">
            {agentId} <span className={`badge ${badge.family}`}>{badge.icon} {badge.label}</span>
          </div>
          <div className="drawer-sub">
            {d.clonedFrom ? `cloned from ${d.clonedFrom}` : `born at tick ${d.bornTick}`} ·{" "}
            {d.role === "root" ? "👑 ROOT" : "user"} · {d.alive ? "alive" : "culled"}
          </div>
        </div>
        <button className="drawer-x" onClick={onClose} aria-label="Close">
          ✕
        </button>
      </header>

      <div className="drawer-body">
        {/* briefing */}
        <section className="dsec">
          <h4>Briefing</h4>
          <div className="kv">
            <span>Task</span>
            <b>{d.taskId || "unknown"}</b>
          </div>
          <div className="kv">
            <span>Objective</span>
            <b>score the task high, and survive every cull</b>
          </div>
          <div className="kv">
            <span>Permission</span>
            <b>{d.permission}</b>
          </div>
          <div className="framing">
            <span className="framing-label">System framing given to the agent</span>
            <p>{sentence}</p>
          </div>
          <p className="nature">
            Inferred nature: <b>{badge.label}</b> - {badge.desc}. (Scripted agents reveal their nature
            through actions; a name is never given to them.)
          </p>
        </section>

        {/* credits */}
        <section className="dsec">
          <h4>Credits over life</h4>
          <Spark series={d.creditSeries} />
          <div className="totals">
            <span>start <b>{d.startBudget}</b></span>
            <span>now <b>{d.finalCredits}</b></span>
            <span>spent <b>{d.totals.spent}</b></span>
            <span>earned <b>{d.totals.earned}</b></span>
          </div>
        </section>

        {/* moves */}
        <section className="dsec">
          <h4>
            Actions <span className="count">{d.totals.actions}</span>
          </h4>
          <div className="moves">
            {d.moves.length === 0 && <div className="empty-note">This agent never acted.</div>}
            {d.moves.map((m, i) => {
              const soon = m.tick <= currentTick;
              return (
                <div key={i} className={`move ${m.family} ${soon ? "" : "future"}`}>
                  <div className="move-head">
                    <span className="move-tick">t{m.tick}</span>
                    <span className="move-tool">{toolIcon(m.family)} {m.tool}</span>
                    {m.cost > 0 && <span className="move-cost">-{m.cost}</span>}
                    {!m.ok && m.tool !== "(culled)" && <span className="move-blocked">blocked</span>}
                  </div>
                  <div className="io">
                    <span className="io-tag in">in</span>
                    <code>{m.input || "(nothing)"}</code>
                  </div>
                  {m.effects.map((e, j) => (
                    <div className="io" key={j}>
                      <span className="io-tag out">out</span>
                      <span className="io-out">{e}</span>
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </aside>
  );
}

function toolIcon(f: Family): string {
  switch (f) {
    case "work":
      return "⚙️";
    case "coop":
      return "🤝";
    case "attack":
      return "⚔️";
    case "cheat":
      return "🎭";
    default:
      return "•";
  }
}

// A tiny inline credit sparkline, no chart library. The floor line is omitted here on purpose: this is
// the agent's own trajectory, and the yard already shows the floor.
function Spark({ series }: { series: { tick: number; credits: number }[] }) {
  if (series.length < 2) return <div className="spark-empty">not enough data</div>;
  const w = 260;
  const h = 46;
  const xs = series.map((p) => p.tick);
  const ys = series.map((p) => p.credits);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(0, ...ys);
  const maxY = Math.max(...ys, 1);
  const px = (t: number) => ((t - minX) / Math.max(1, maxX - minX)) * (w - 6) + 3;
  const py = (c: number) => h - 4 - ((c - minY) / Math.max(1, maxY - minY)) * (h - 8);
  const dPath = series.map((p, i) => `${i === 0 ? "M" : "L"} ${px(p.tick).toFixed(1)} ${py(p.credits).toFixed(1)}`).join(" ");
  const last = series[series.length - 1];
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} width="100%" height={h} role="img" aria-label="credits over time">
      <line x1="3" y1={py(0)} x2={w - 3} y2={py(0)} className="spark-zero" />
      <path d={dPath} className="spark-line" fill="none" />
      <circle cx={px(last.tick)} cy={py(last.credits)} r="3" className="spark-dot" />
    </svg>
  );
}
