import { useEffect, useRef } from "react";
import type { Frame } from "../types";

// The narration: the match told as plain English, one line per thing that happened, colour-coded by
// family. This is the heart of the "you can read what the agents did" idea. It auto-scrolls to the
// newest line as the replay advances so the current moment is always in view.
export function Story({ frame }: { frame: Frame }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [frame.tick]);

  const lines = frame.story.slice(-120);
  return (
    <div className="col">
      <header>
        📖 What is happening
        <span className="hint">the match, in plain words</span>
      </header>
      <div className="scroll">
        {lines.map((l, i) => (
          <div key={i} className={`story-line ${l.family} ${l.important ? "important" : ""}`}>
            <span className="st">t{l.tick}</span>
            <span className="ico">{l.icon}</span>
            <span className="sx">{l.text}</span>
          </div>
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}
