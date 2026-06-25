import { useEffect, useRef } from "react";
import { Epic, Usage, UserStory } from "../types";
import { useI18n } from "../i18n/i18n";
import { epicProgress, EpicProgressBar } from "./Board";

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

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
  const { t } = useI18n();
  const STATUS_LABEL: Record<string, string> = {
    todo: t("iterationsView.statusTodo"),
    in_progress: t("iterationsView.statusInProgress"),
    red: t("iterationsView.statusRed"),
    green: t("iterationsView.statusGreen"),
    done: t("iterationsView.statusDone"),
    failed: t("iterationsView.statusFailed"),
  };
  const STATE_LABEL: Record<string, string> = {
    working: t("iterationsView.stateWorking"),
    done: t("iterationsView.stateDone"),
    failed: t("iterationsView.stateFailed"),
    pending: t("iterationsView.statePending"),
  };
  const iters = [...new Set(epics.map((e) => e.iteration))].sort((a, b) => b - a);
  const focusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    // `?.` sur la méthode : scrollIntoView n'existe pas sous jsdom (tests).
    focusRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }, [focusIter]);

  return (
    <div className="panel iterations">
      <div className="board-top">
        <h2>{t("iterationsView.title")}</h2>
        <span className="iter-hint">{t("iterationsView.hint")}</span>
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
                  {t("iterationsView.iteration", { n })}
                </span>
                <span className={`iter-state state-${prog.state}`}>
                  {STATE_LABEL[prog.state] ?? prog.state}
                </span>
                <span className="iter-counts">
                  {t(
                    iterEpics.length > 1
                      ? "iterationsView.countsMany"
                      : "iterationsView.countsOne",
                    { epics: iterEpics.length, done: prog.done, total: prog.total },
                  )}
                </span>
              </header>

              <EpicProgressBar prog={prog} />

              {usage && (
                <div className="iter-usage" title={t("iterationsView.usageTitle")}>
                  💰 ${usage.cost_usd.toFixed(4)} · 🔢{" "}
                  {formatTokens(usage.input_tokens + usage.output_tokens)} tok ·{" "}
                  {t(
                    usage.agent_calls > 1
                      ? "iterationsView.usageMany"
                      : "iterationsView.usageOne",
                    { calls: usage.agent_calls },
                  )}
                </div>
              )}

              {iterEpics.length > 0 && (
                <div className="iter-epics">
                  {iterEpics.map((e) => (
                    <button
                      key={e.id}
                      type="button"
                      className="iter-epic-chip"
                      title={t("iterationsView.openEpicTitle", { id: e.id })}
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
                        title={t("iterationsView.openStoryTitle", { id: s.id })}
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
                <p className="placeholder small">{t("iterationsView.noStories")}</p>
              )}

              {canRollback && (
                <div className="iter-card-actions">
                  <button
                    type="button"
                    className="ghost small-btn"
                    title={t("iterationsView.rollbackTitle", { n })}
                    onClick={() => onRollbackTo!(n)}
                  >
                    {t("iterationsView.rollbackButton")}
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
