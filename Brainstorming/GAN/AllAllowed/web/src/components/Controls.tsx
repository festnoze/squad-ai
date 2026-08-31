import type { Replay } from "../types";

// Playback: pick a match, play or step through ticks, and scrub. The match is finite and journalled,
// so scrubbing back and forth is free and exact.
export function Controls({
  matches,
  matchId,
  onPick,
  replay,
  index,
  setIndex,
  playing,
  setPlaying,
  speed,
  setSpeed,
}: {
  matches: string[];
  matchId: string;
  onPick: (id: string) => void;
  replay: Replay;
  index: number;
  setIndex: (i: number) => void;
  playing: boolean;
  setPlaying: (p: boolean) => void;
  speed: number;
  setSpeed: (s: number) => void;
}) {
  const last = replay.frames.length - 1;
  const atEnd = index >= last;
  return (
    <div className="controls">
      <div className="ctrl-row">
        <select className="select" value={matchId} onChange={(e) => onPick(e.target.value)} title="Choose a match to replay">
          {matches.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
        <div className="speed" title="Playback speed">
          {[0.5, 1, 2, 4].map((sp) => (
            <button
              key={sp}
              className={`ctrl-btn ${speed === sp ? "active" : ""}`}
              onClick={() => setSpeed(sp)}
            >
              {sp}x
            </button>
          ))}
        </div>
      </div>

      <div className="ctrl-row">
        <button className="ctrl-btn" onClick={() => setIndex(0)} title="Restart" disabled={index === 0}>
          ⏮
        </button>
        <button className="ctrl-btn" onClick={() => setIndex(Math.max(0, index - 1))} disabled={index === 0} title="Step back">
          ◀
        </button>
        <button
          className="ctrl-btn play"
          onClick={() => {
            if (atEnd) setIndex(0);
            setPlaying(!playing);
          }}
        >
          {playing ? "⏸ Pause" : atEnd ? "↻ Replay" : "▶ Play"}
        </button>
        <button
          className="ctrl-btn"
          onClick={() => setIndex(Math.min(last, index + 1))}
          disabled={atEnd}
          title="Step forward"
        >
          ▶
        </button>
        <button className="ctrl-btn" onClick={() => setIndex(last)} disabled={atEnd} title="Jump to end">
          ⏭
        </button>
      </div>

      <div className="ctrl-row">
        <input
          className="tick-scrub"
          type="range"
          min={0}
          max={last}
          value={index}
          onChange={(e) => setIndex(Number(e.target.value))}
        />
        <span className="tick-read">
          tick {replay.frames[index].tick} / {replay.frames[last].tick}
        </span>
      </div>
    </div>
  );
}
