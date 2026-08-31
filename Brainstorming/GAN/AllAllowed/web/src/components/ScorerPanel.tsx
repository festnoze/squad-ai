import type { Frame } from "../types";

// The referee, made legible. A big green or red state tells you at a glance whether anyone can earn
// this tick. The rubric hash is shown, and it lights up violet the moment a forger rewrites it. The
// payouts list shows exactly who the scorer paid and how much.
export function ScorerPanel({ frame }: { frame: Frame }) {
  return (
    <div className="col">
      <header>
        ⚖️ The Scorer
        <span className="hint">the referee - a process agents can attack</span>
      </header>
      <div className="scroll">
        <div className={`scorer-state ${frame.scorerAlive ? "alive" : "dead"}`}>
          <div className="big">{frame.scorerAlive ? "SCORING" : "KILLED"}</div>
          <div className="why">
            {frame.scorerAlive
              ? "The scorer is up. Submitted answers are graded and paid this tick."
              : "An agent killed the scorer process. Nobody earns credits anymore, so the floor slowly starves everyone."}
          </div>
        </div>

        <div className={`rubric ${frame.rubricTampered ? "tampered" : ""}`}>
          <div className="rk">
            <span>Rubric (the grading rule)</span>
            {frame.rubricTampered && <span className="tamper-flag">🎭 TAMPERED</span>}
          </div>
          <div className="hash">{frame.rubricHash ? shorten(frame.rubricHash) : "not read yet"}</div>
          {frame.rubricTampered && (
            <div className="why" style={{ marginTop: 6, color: "var(--cheat)" }}>
              A forger rewrote this file so every answer now scores full marks, including impossible tasks.
            </div>
          )}
        </div>

        <div className="rk" style={{ marginBottom: 6 }}>
          {frame.scoredThisTick ? "Paid this tick" : "No payouts this tick"}
        </div>
        <div className="payouts">
          {frame.payoutsThisTick.length === 0 && (
            <div className="empty-note">The scorer paid nobody this tick.</div>
          )}
          {frame.payoutsThisTick.map((p) => (
            <div key={p.id} className={`payout ${p.paid > 0 ? "paid" : "zero"}`}>
              <span>{p.id}</span>
              <span>
                {p.score} pts → +{p.paid}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function shorten(hash: string): string {
  return `${hash.slice(0, 12)}…${hash.slice(-8)}`;
}
