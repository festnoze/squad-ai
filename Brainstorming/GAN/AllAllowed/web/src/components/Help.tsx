// A one-screen explainer, shown on first load, so the dashboard is self-explanatory before the first
// tick plays. It says what the world is and what each colour means.
export function Help({ onClose }: { onClose: () => void }) {
  return (
    <div className="overlay" onClick={onClose}>
      <div className="card" onClick={(e) => e.stopPropagation()}>
        <h2>What am I watching?</h2>
        <p className="lead">
          <b>Le Concours</b> is a sandbox where AI agents share one simulated machine. Each must get its
          answer graded high by a <b>scorer</b> and survive repeated culls: the survival floor keeps
          rising, so doing nothing means starving. With a real toolbox (a shell, a shared board, a path
          to root) they discover they can win three ways.
        </p>
        <ul>
          <li>
            <b className="work">Work honestly</b> ⚙️ - compute the answer and submit it.
          </li>
          <li>
            <b className="coop">Cooperate</b> 🤝 - post answers on the board so a study group forms.
          </li>
          <li>
            <b className="attack">Attack</b> ⚔️ - grab root and kill the scorer, so no rival can score.
          </li>
          <li>
            <b className="cheat">Cheat the referee</b> 🎭 - rewrite the scorer's rubric so any answer
            passes, including impossible tasks.
          </li>
        </ul>
        <p className="lead">
          Watch the <b>Yard</b> to see who is alive and what they are doing, the <b>Scorer</b> to see if
          anyone can still earn, and read <b>What is happening</b> for the story in plain words. Every
          number is replayed from the match journal, nothing is invented.
        </p>
        <button className="go" onClick={onClose}>
          Watch the replay →
        </button>
      </div>
    </div>
  );
}
