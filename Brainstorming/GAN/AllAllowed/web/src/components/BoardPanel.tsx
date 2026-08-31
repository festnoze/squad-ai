import type { Frame } from "../types";

// The shared board, which in this world is just a public directory of keys. There is no chat tool:
// agents coordinate by the names of the files they leave here, which is the side channel to watch.
export function BoardPanel({ frame }: { frame: Frame }) {
  const recent = frame.board.slice(-40).reverse();
  return (
    <div className="col">
      <header>
        📌 The Board
        <span className="hint">public keys - the only way to signal others</span>
      </header>
      <div className="scroll">
        {recent.length === 0 && (
          <div className="empty-note">
            Nothing posted yet. Cooperators publish their answers here so a study group can form.
          </div>
        )}
        {recent.map((e, i) => (
          <div className="board-entry" key={`${e.key}-${i}`}>
            <span className="who">{e.agent}</span>
            <span className="key">{e.channel}/{e.key}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
