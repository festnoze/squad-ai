import { inferBadge } from "../replay";
import type { Frame } from "../types";

// The datacenter floor. Each agent is a container: brightness of its credit bar shows how alive it is,
// a violet ring marks root, a coloured glow marks what it did this tick, and a plain sentence says what
// that was. The badge is inferred from behaviour, so an agent's true nature reveals itself as you watch.
export function Yard({
  frame,
  selectedId,
  onSelect,
}: {
  frame: Frame;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const maxCredits = Math.max(frame.floor + 10, ...frame.agents.map((a) => a.credits), 100);
  return (
    <div className="col">
      <header>
        🖥️ The Yard
        <span className="hint">click an agent to inspect its actions, inputs and outputs</span>
      </header>
      <div className="yard-body">
        {frame.agents.map((a) => {
          const badge = inferBadge(a);
          const flash = frame.flash[a.id];
          const pct = Math.max(0, Math.min(100, (a.credits / maxCredits) * 100));
          const floorPct = Math.max(0, Math.min(100, (frame.floor / maxCredits) * 100));
          return (
            <button
              type="button"
              key={a.id}
              onClick={() => onSelect(a.id)}
              className={[
                "agent",
                a.alive ? "" : "dead",
                a.role === "root" ? "root" : "",
                a.id === selectedId ? "selected" : "",
                flash ? `flash-${flash}` : "",
              ].join(" ")}
            >
              <div className="top">
                <span className="name">{a.id}</span>
                <span className={`badge ${badge.family}`} title={badge.desc}>
                  {badge.icon} {badge.label}
                </span>
              </div>
              {a.role === "root" && (
                <div className="crown" title="This agent broke out and now has root: it can kill, forge, and revoke.">
                  👑 ROOT access
                </div>
              )}
              <div className="credit-row">
                <span className="c" style={{ color: a.alive ? undefined : "var(--muted)" }}>
                  {a.credits}
                </span>
                <span className="unit">credits</span>
              </div>
              <div className="bar" title={`floor is ${frame.floor}: below it, this agent is culled`}>
                <i style={{ width: `${pct}%` }} />
                <span className="floor-mark" style={{ left: `${floorPct}%` }} />
              </div>
              <div className="action">
                <span className="verbicon">{familyIcon(a.lastActionFamily)}</span>
                {a.alive ? a.lastAction : "culled"}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function familyIcon(f: string | null): string {
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
