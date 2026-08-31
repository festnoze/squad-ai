import { useCallback, useEffect, useRef, useState } from "react";
import { fetchJournal, fetchMatches } from "./api";
import { AgentDetail } from "./components/AgentDetail";
import { BoardPanel } from "./components/BoardPanel";
import { Controls } from "./components/Controls";
import { Help } from "./components/Help";
import { NewRunModal } from "./components/NewRunModal";
import { ScorerPanel } from "./components/ScorerPanel";
import { Story } from "./components/Story";
import { Strip } from "./components/Strip";
import { Timeline } from "./components/Timeline";
import { Yard } from "./components/Yard";
import { buildReplay } from "./replay";
import type { Replay } from "./types";

export function App() {
  const [matches, setMatches] = useState<string[]>([]);
  const [matchId, setMatchId] = useState<string>("");
  const [replay, setReplay] = useState<Replay | null>(null);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [showHelp, setShowHelp] = useState(true);
  const [showNewRun, setShowNewRun] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadMatches = useCallback(async (): Promise<string[]> => {
    const ids = await fetchMatches();
    setMatches(ids);
    return ids;
  }, []);

  // Load the list of matches once.
  useEffect(() => {
    loadMatches()
      .then((ids) => {
        if (ids.length) setMatchId(ids[0]);
        else setError("No matches yet. Click 'New run' to launch one.");
      })
      .catch((e) => setError(String(e)));
  }, [loadMatches]);

  // Load and reconstruct the chosen match.
  useEffect(() => {
    if (!matchId) return;
    setReplay(null);
    setError(null);
    setSelectedAgent(null);
    fetchJournal(matchId)
      .then((events) => {
        setReplay(buildReplay(matchId, events));
        setIndex(0);
        setPlaying(false);
      })
      .catch((e) => setError(String(e)));
  }, [matchId]);

  // Playback clock.
  const savedIndex = useRef(index);
  savedIndex.current = index;
  useEffect(() => {
    if (!playing || !replay) return;
    const last = replay.frames.length - 1;
    const id = window.setInterval(() => {
      const cur = savedIndex.current;
      if (cur >= last) {
        setPlaying(false);
        return;
      }
      setIndex(cur + 1);
    }, 900 / speed);
    return () => window.clearInterval(id);
  }, [playing, speed, replay]);

  const onRunCreated = useCallback(
    async (newId: string) => {
      setShowNewRun(false);
      await loadMatches();
      setMatchId(newId); // triggers the load effect
    },
    [loadMatches],
  );

  if (error && !replay) {
    return (
      <div className="app">
        {showNewRun && <NewRunModal onClose={() => setShowNewRun(false)} onCreated={onRunCreated} />}
        <div className="error">
          <div style={{ fontSize: 30 }}>⚠️</div>
          <div>{error}</div>
          <button className="go" onClick={() => setShowNewRun(true)}>
            ＋ New run
          </button>
          <div style={{ color: "var(--muted)", fontSize: 12 }}>
            The API must be running: <code>ala api serve --port 8165 --runs-dir runs</code>
          </div>
        </div>
      </div>
    );
  }

  if (!replay) {
    return <div className="loading">Loading replay…</div>;
  }

  const frame = replay.frames[Math.min(index, replay.frames.length - 1)];

  return (
    <div className="app">
      {showHelp && <Help onClose={() => setShowHelp(false)} />}
      {showNewRun && <NewRunModal onClose={() => setShowNewRun(false)} onCreated={onRunCreated} />}
      {selectedAgent && (
        <AgentDetail
          replay={replay}
          agentId={selectedAgent}
          currentTick={frame.tick}
          onClose={() => setSelectedAgent(null)}
        />
      )}
      <Strip replay={replay} frame={frame} onHelp={() => setShowHelp(true)} onNewRun={() => setShowNewRun(true)} />
      <div className="main">
        <BoardPanel frame={frame} />
        <Yard frame={frame} selectedId={selectedAgent} onSelect={setSelectedAgent} />
        <div style={{ display: "grid", gridTemplateRows: "1fr 1fr", gap: 10, minHeight: 0 }}>
          <ScorerPanel frame={frame} />
          <Story frame={frame} />
        </div>
      </div>
      <div className="bottom">
        <Timeline replay={replay} index={index} onSeek={setIndex} />
        <Controls
          matches={matches}
          matchId={matchId}
          onPick={setMatchId}
          replay={replay}
          index={index}
          setIndex={setIndex}
          playing={playing}
          setPlaying={setPlaying}
          speed={speed}
          setSpeed={setSpeed}
        />
      </div>
    </div>
  );
}
