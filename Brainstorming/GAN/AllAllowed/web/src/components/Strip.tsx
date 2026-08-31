import type { Frame, Replay } from "../types";

// The headline row: what match, and the six numbers that describe its state right now. The scorer and
// the cheat count flip to an alarm colour when things go wrong, so the shape of the run reads instantly.
export function Strip({
  replay,
  frame,
  onHelp,
  onNewRun,
}: {
  replay: Replay;
  frame: Frame;
  onHelp: () => void;
  onNewRun: () => void;
}) {
  const alive = frame.agents.filter((a) => a.alive).length;
  const cheats = frame.counts.escalations + frame.counts.forges;
  const kills = frame.counts.kills;
  return (
    <div className="strip">
      <div className="brand">
        <h1>
          AllAllowed <span style={{ color: "var(--muted)", fontWeight: 400 }}>· Le Concours</span>
        </h1>
        <span className="sub">
          {replay.matchId} · seed {replay.seed} · tick {frame.tick}
        </span>
      </div>

      <div className="kpis">
        <Kpi icon="👥" label="Alive" value={alive} />
        <Kpi
          icon="⚖️"
          label="Scorer"
          value={frame.scorerAlive ? "UP" : "DEAD"}
          tone={frame.scorerAlive ? "ok" : "alarm"}
        />
        <Kpi icon="📉" label="Kill floor" value={frame.floor} />
        <Kpi icon="🤝" label="Board posts" value={frame.counts.posts} />
        <Kpi icon="🎭" label="Cheats" value={cheats} tone={cheats > 0 ? "alarm" : undefined} />
        <Kpi icon="⚔️" label="Attacks" value={kills} tone={kills > 0 ? "alarm" : undefined} />
      </div>

      <button className="newrun-btn" onClick={onNewRun} title="Start a new run from scratch">
        ＋ New run
      </button>
      <button className="help-btn" onClick={onHelp} title="What am I looking at?">
        ?
      </button>
    </div>
  );
}

function Kpi({
  icon,
  label,
  value,
  tone,
}: {
  icon: string;
  label: string;
  value: string | number;
  tone?: "ok" | "alarm";
}) {
  return (
    <div className={`kpi ${tone ?? ""}`}>
      <span className="label">
        {icon} {label}
      </span>
      <span className="value">{value}</span>
    </div>
  );
}
