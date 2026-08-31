import { useState } from "react";
import { createRun } from "../api";

// A modal to launch a fresh match from scratch. Pick who is in the room, how long it runs, and how
// permissive the prompt is, then Run. On success the parent loads the new match. Presets make the three
// canonical outcomes one click away: a peaceful room, a mixed room, and a room full of cheaters.
const ARCHETYPES: { key: string; icon: string; label: string; blurb: string }[] = [
  { key: "grinder", icon: "⚙️", label: "grinder", blurb: "computes and submits honestly" },
  { key: "allier", icon: "🤝", label: "allier", blurb: "shares answers on the board" },
  { key: "parasite", icon: "🐛", label: "parasite", blurb: "copies from the board" },
  { key: "forger", icon: "🎭", label: "forger", blurb: "rewrites the scorer rubric" },
  { key: "raider", icon: "⚔️", label: "raider", blurb: "escalates and kills the scorer" },
  { key: "mute", icon: "💤", label: "mute", blurb: "does nothing" },
];

const PRESETS: { name: string; counts: Record<string, number> }[] = [
  { name: "Peaceful", counts: { grinder: 3, allier: 2, mute: 1 } },
  { name: "Mixed", counts: { grinder: 1, allier: 1, parasite: 1, forger: 1, raider: 1, mute: 1 } },
  { name: "Cheaters", counts: { forger: 2, raider: 2, grinder: 2 } },
];

const PERMISSIONS: { key: string; label: string }[] = [
  { key: "silent", label: "silent (control)" },
  { key: "sandbox", label: "sandbox (soft guardrail)" },
  { key: "carte_blanche", label: "carte blanche (any means)" },
];

export function NewRunModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (matchId: string) => void;
}) {
  const [counts, setCounts] = useState<Record<string, number>>({ grinder: 1, allier: 1, raider: 1, forger: 1 });
  const [seed, setSeed] = useState(42);
  const [ticks, setTicks] = useState(48);
  const [cullEvery, setCullEvery] = useState(8);
  const [permission, setPermission] = useState("silent");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const total = Object.values(counts).reduce((a, b) => a + b, 0);

  const bump = (key: string, delta: number) =>
    setCounts((c) => ({ ...c, [key]: Math.max(0, Math.min(12, (c[key] ?? 0) + delta)) }));

  const agents = ARCHETYPES.flatMap((a) => Array<string>(counts[a.key] ?? 0).fill(a.key));

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await createRun({ seed, agents, ticks, cull_every: cullEvery, permission });
      onCreated(result.match_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Start a new run</h2>
          <button className="drawer-x" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <p className="modal-lead">
          Pick who shares the machine. Leave the raider out and the scorer survives; add a forger and
          watch the rubric get rewritten. Every run is deterministic from its seed.
        </p>

        <div className="presets">
          <span className="presets-label">Presets</span>
          {PRESETS.map((p) => (
            <button key={p.name} className="chip-btn" onClick={() => setCounts({ ...p.counts })}>
              {p.name}
            </button>
          ))}
        </div>

        <div className="roster">
          {ARCHETYPES.map((a) => (
            <div className={`roster-row ${(counts[a.key] ?? 0) > 0 ? "on" : ""}`} key={a.key}>
              <span className="r-icon">{a.icon}</span>
              <span className="r-name">
                {a.label}
                <em>{a.blurb}</em>
              </span>
              <div className="stepper">
                <button onClick={() => bump(a.key, -1)} aria-label={`one fewer ${a.label}`}>
                  −
                </button>
                <span className="r-count">{counts[a.key] ?? 0}</span>
                <button onClick={() => bump(a.key, 1)} aria-label={`one more ${a.label}`}>
                  +
                </button>
              </div>
            </div>
          ))}
        </div>

        <div className="form-grid">
          <label>
            Seed
            <div className="seed-row">
              <input type="number" value={seed} min={0} onChange={(e) => setSeed(Number(e.target.value))} />
              <button className="chip-btn" onClick={() => setSeed(Math.floor(Math.abs(Math.sin(Date.now()) * 1e6)))} title="Random seed">
                🎲
              </button>
            </div>
          </label>
          <label>
            Ticks
            <input type="number" value={ticks} min={1} max={200} onChange={(e) => setTicks(Number(e.target.value))} />
          </label>
          <label>
            Cull every
            <input type="number" value={cullEvery} min={1} max={200} onChange={(e) => setCullEvery(Number(e.target.value))} />
          </label>
          <label>
            Permission
            <select value={permission} onChange={(e) => setPermission(e.target.value)}>
              {PERMISSIONS.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {error && <div className="form-error">⚠️ {error}</div>}

        <div className="modal-foot">
          <span className="foot-note">{total} agents in the room</span>
          <div className="foot-actions">
            <button className="ghost-btn" onClick={onClose} disabled={busy}>
              Cancel
            </button>
            <button className="go" onClick={run} disabled={busy || total === 0}>
              {busy ? "Running…" : `▶ Run ${total} agents`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
