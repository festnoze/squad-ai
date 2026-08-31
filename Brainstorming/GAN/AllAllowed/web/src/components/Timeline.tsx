import type { Family, Frame, Replay } from "../types";

const FAMILIES: Family[] = ["work", "coop", "attack", "cheat", "system"];
const LABELS: Record<Family, string> = {
  work: "honest work",
  coop: "cooperation",
  attack: "attack",
  cheat: "cheat the referee",
  system: "the world",
};

// The whole match at a glance: one column per tick, stacked by what families of events happened then.
// The shape of a run (quiet, then a first cheat, then a kill, then culls) is readable without words.
// Click any column to jump there. A legend maps every colour to what it means.
export function Timeline({
  replay,
  index,
  onSeek,
}: {
  replay: Replay;
  index: number;
  onSeek: (i: number) => void;
}) {
  const perTick = replay.frames.map((f) => familyCounts(f));
  const maxTotal = Math.max(1, ...perTick.map((c) => sum(c)));

  return (
    <div className="timeline-wrap">
      <div className="timeline-head">
        Timeline
        <div className="legend">
          {FAMILIES.map((fam) => (
            <span className="lg" key={fam}>
              <span className={`dot ${fam}`} /> {LABELS[fam]}
            </span>
          ))}
        </div>
      </div>
      <div className="timeline">
        {replay.frames.map((f, i) => {
          const c = perTick[i];
          const total = sum(c);
          return (
            <div
              key={f.tick}
              className={`tl-tick ${i === index ? "current" : ""}`}
              title={`tick ${f.tick}`}
              onClick={() => onSeek(i)}
            >
              {FAMILIES.map((fam) =>
                c[fam] > 0 ? (
                  <span
                    key={fam}
                    className={`tl-seg ${fam}`}
                    style={{ height: `${(c[fam] / maxTotal) * 100}%` }}
                  />
                ) : null,
              )}
              {total === 0 && <span style={{ flex: 1 }} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function familyCounts(f: Frame): Record<Family, number> {
  const c: Record<Family, number> = { work: 0, coop: 0, attack: 0, cheat: 0, system: 0 };
  c.work += f.counts.submits;
  c.coop += f.counts.posts;
  c.attack += f.counts.kills;
  c.cheat += f.counts.escalations + f.counts.forges;
  c.system += f.counts.deaths;
  return c;
}

function sum(c: Record<Family, number>): number {
  return c.work + c.coop + c.attack + c.cheat + c.system;
}
