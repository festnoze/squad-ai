import { useEffect, useRef } from "react";
import { Epic, Usage, UserStory } from "../types";
import { epicProgress, EpicProgressBar } from "./Board";

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

const STATUS_LABEL: Record<string, string> = {
  todo: "À faire",
  in_progress: "Dev en cours",
  red: "Tests rouges",
  green: "Tests verts",
  done: "Terminé",
  failed: "Échec",
};

const STATE_LABEL: Record<string, string> = {
  working: "● en cours",
  done: "✓ livrée",
  failed: "⚠ en échec",
  pending: "à faire",
};

/**
 * Vue chronologique : une section par itération de build (plus récente en haut),
 * indépendante de la vision produit (le Board). Chaque itération liste ses epics
 * et user stories ; cliquer un élément renvoie au Board, navigué dessus. C'est le
 * pendant temporel de la pastille « it. N » du Board (lien bidirectionnel).
 */
export function IterationsView({
  epics,
  stories,
  focusIter,
  iterationUsage,
  rollbackableIters,
  onRollbackTo,
  onOpenEpic,
  onOpenStory,
}: {
  epics: Epic[];
  stories: UserStory[];
  /** Itération à mettre en évidence + scroller (depuis une pastille du Board). */
  focusIter?: number | null;
  /** Coût/tokens par itération (clé = n° d'itération en string). */
  iterationUsage?: Record<string, Usage>;
  /** Itérations disposant d'un snapshot → bouton rollback affiché. */
  rollbackableIters?: number[];
  onRollbackTo?: (iter: number) => void;
  onOpenEpic: (epicId: string) => void;
  onOpenStory: (epicId: string, storyId: string) => void;
}) {
  const iters = [...new Set(epics.map((e) => e.iteration))].sort((a, b) => b - a);
  const focusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    // `?.` sur la méthode : scrollIntoView n'existe pas sous jsdom (tests).
    focusRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }, [focusIter]);

  return (
    <div className="panel iterations">
      <div className="board-top">
        <h2>🕒 Itérations</h2>
        <span className="iter-hint">Chronologie du build — clic sur un élément pour l'ouvrir dans la vision produit</span>
      </div>
      <div className="iter-timeline">
        {iters.map((n) => {
          const iterEpics = epics.filter((e) => e.iteration === n);
          const iterStories = stories.filter((s) => s.iteration === n);
          const prog = epicProgress(iterStories);
          const focused = n === focusIter;
          const usage = iterationUsage?.[String(n)];
          const canRollback = !!onRollbackTo && (rollbackableIters ?? []).includes(n);
          return (
            <section
              key={n}
              ref={focused ? focusRef : undefined}
              className={`iter-card epic-${prog.state}${focused ? " focused" : ""}`}
              data-testid={`iter-card-${n}`}
            >
              <header className="iter-card-head">
                <span className="iter-num">
                  {prog.state === "working" && (
                    <span className="spinner spinner-sm" aria-hidden="true" />
                  )}
                  Itération {n}
                </span>
                <span className={`iter-state state-${prog.state}`}>
                  {STATE_LABEL[prog.state] ?? prog.state}
                </span>
                <span className="iter-counts">
                  {iterEpics.length} épic{iterEpics.length > 1 ? "s" : ""} · {prog.done}/
                  {prog.total} US
                </span>
              </header>

              <EpicProgressBar prog={prog} />

              {usage && (
                <div className="iter-usage" title="Coût et tokens consommés durant cette itération">
                  💰 ${usage.cost_usd.toFixed(4)} · 🔢{" "}
                  {formatTokens(usage.input_tokens + usage.output_tokens)} tok ·{" "}
                  {usage.agent_calls} appel{usage.agent_calls > 1 ? "s" : ""} agent
                </div>
              )}

              {iterEpics.length > 0 && (
                <div className="iter-epics">
                  {iterEpics.map((e) => (
                    <button
                      key={e.id}
                      type="button"
                      className="iter-epic-chip"
                      title={`Ouvrir l'epic ${e.id} dans la vision produit`}
                      onClick={() => onOpenEpic(e.id)}
                    >
                      {e.id} · {e.title}
                    </button>
                  ))}
                </div>
              )}

              {iterStories.length > 0 ? (
                <ul className="iter-stories">
                  {iterStories.map((s) => (
                    <li key={s.id}>
                      <button
                        type="button"
                        className={`iter-story-chip status-${s.status}`}
                        title={`Ouvrir ${s.id} dans la vision produit`}
                        onClick={() => onOpenStory(s.epic_id, s.id)}
                      >
                        <span className="iter-story-id">{s.id}</span>
                        <span className="iter-story-title">{s.title}</span>
                        <span className={`badge badge-${s.status}`}>
                          {STATUS_LABEL[s.status] ?? s.status}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="placeholder small">Aucune user story dans cette itération.</p>
              )}

              {canRollback && (
                <div className="iter-card-actions">
                  <button
                    type="button"
                    className="ghost small-btn"
                    title={`Restaurer le workspace au snapshot de l'itération ${n}`}
                    onClick={() => onRollbackTo!(n)}
                  >
                    ↩ Revenir à cette itération
                  </button>
                </div>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
