import { useEffect, useMemo, useState } from "react";
import { getIterations } from "../api";
import { Epic, ProjectTicks, Stream, Usage, UserStory } from "../types";
import { Activity } from "./Activity";
import { Board } from "./Board";
import { IterationsView } from "./IterationsView";

type View = "vision" | "iterations" | "activity";

/**
 * Conteneur des deux lentilles sur le même produit :
 * - « Vision produit » : le Board (epics/US) à plat, indépendant des itérations ;
 * - « Itérations » : la chronologie du build.
 * Coordonne les liens croisés : une pastille « it. N » du Board ouvre la
 * chronologie sur N ; un élément de la chronologie renvoie au Board, navigué
 * dessus. La bascule n'apparaît qu'à partir de 2 itérations (sinon la vision
 * suffit — la plupart des projets en mode interview n'en ont qu'une).
 */
export function WorkspaceViews({
  epics,
  stories,
  streams,
  projectId,
  phase,
  iterationUsage,
  onRollbackTo,
  ticks,
  awaitingApproval,
  onApprove,
  onReject,
}: {
  epics: Epic[];
  stories: UserStory[];
  /** ST-12: declared streams (empty/absent = legacy single-stream project). */
  streams?: Stream[];
  projectId: string;
  phase?: string;
  /** Coût/tokens par itération (clé = n° d'itération en string), pour la timeline. */
  iterationUsage?: Record<string, Usage>;
  /** Rollback vers une itération (gère confirmation + toast côté App). */
  onRollbackTo?: (iter: number) => void;
  /** B-UX: live heartbeat for THIS project (item-level stage/persona/recovery +
   * counts/stall). Optional; absent outside BUILD or before the first tick. */
  ticks?: ProjectTicks;
  /** P13: the approval gate string (`awaiting_approval`) surfaced as a banner in
   * the Activity scene. Empty/absent = no gate. */
  awaitingApproval?: string;
  onApprove?: () => void;
  onReject?: () => void;
}) {
  // P6/B-UX: Activité is the default lens during BUILD; Board + Iterations stay
  // available. Outside build the historic "vision produit" remains the default.
  const [view, setView] = useState<View>(phase === "build" ? "activity" : "vision");
  const [boardFocus, setBoardFocus] = useState<{ epicId: string; storyId?: string } | null>(
    null,
  );
  const [iterFocus, setIterFocus] = useState<number | null>(null);
  // Itérations disposant d'un snapshot git (donc « rollback-ables »). Rafraîchi
  // quand le projet ou le nombre d'itérations change (un nouveau snapshot naît
  // à la fin de chaque itération).
  const [snapshotIters, setSnapshotIters] = useState<number[]>([]);

  const iterCount = useMemo(
    () => new Set(epics.map((e) => e.iteration)).size,
    [epics],
  );
  const multiIter = iterCount > 1;
  // Iterations is gated on having ≥2 iterations; if the active view is iterations
  // but that's no longer true, fall back to vision.
  const showIterations = view === "iterations" && multiIter;
  const showActivity = view === "activity";

  useEffect(() => {
    if (!onRollbackTo) return; // rollback désactivé : pas la peine de fetch
    let cancelled = false;
    getIterations(projectId)
      .then((iters) => {
        if (!cancelled) setSnapshotIters(iters);
      })
      .catch(() => {
        if (!cancelled) setSnapshotIters([]);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, iterCount, onRollbackTo]);

  const openIteration = (iter: number) => {
    setIterFocus(iter);
    setView("iterations");
  };
  const openStory = (epicId: string, storyId: string) => {
    setBoardFocus({ epicId, storyId });
    setView("vision");
  };
  const openEpic = (epicId: string) => {
    setBoardFocus({ epicId });
    setView("vision");
  };

  return (
    <>
      <div className="view-toggle" role="tablist" aria-label="Vue du projet">
        <button
          type="button"
          role="tab"
          aria-selected={showActivity}
          className={showActivity ? "active" : ""}
          onClick={() => setView("activity")}
        >
          ⚡ Activité
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={!showActivity && !showIterations}
          className={!showActivity && !showIterations ? "active" : ""}
          onClick={() => setView("vision")}
        >
          🗂 Vision produit
        </button>
        {multiIter && (
          <button
            type="button"
            role="tab"
            aria-selected={showIterations}
            className={showIterations ? "active" : ""}
            onClick={() => setView("iterations")}
          >
            🕒 Itérations
          </button>
        )}
      </div>
      {showActivity ? (
        <Activity
          epics={epics}
          stories={stories}
          streams={streams}
          projectId={projectId}
          phase={phase}
          awaitingApproval={awaitingApproval}
          onApprove={onApprove}
          onReject={onReject}
          ticks={ticks}
        />
      ) : showIterations ? (
        <IterationsView
          epics={epics}
          stories={stories}
          focusIter={iterFocus}
          iterationUsage={iterationUsage}
          rollbackableIters={snapshotIters}
          onRollbackTo={onRollbackTo}
          onOpenEpic={openEpic}
          onOpenStory={openStory}
        />
      ) : (
        <Board
          epics={epics}
          stories={stories}
          streams={streams}
          projectId={projectId}
          phase={phase}
          focus={boardFocus}
          onFocusConsumed={() => setBoardFocus(null)}
          onOpenIteration={multiIter ? openIteration : undefined}
        />
      )}
    </>
  );
}
