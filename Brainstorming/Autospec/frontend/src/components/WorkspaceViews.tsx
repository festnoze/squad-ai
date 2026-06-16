import { useEffect, useMemo, useState } from "react";
import { getIterations } from "../api";
import { Epic, Usage, UserStory } from "../types";
import { Board } from "./Board";
import { IterationsView } from "./IterationsView";

type View = "vision" | "iterations";

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
  projectId,
  phase,
  iterationUsage,
  onRollbackTo,
}: {
  epics: Epic[];
  stories: UserStory[];
  projectId: string;
  phase?: string;
  /** Coût/tokens par itération (clé = n° d'itération en string), pour la timeline. */
  iterationUsage?: Record<string, Usage>;
  /** Rollback vers une itération (gère confirmation + toast côté App). */
  onRollbackTo?: (iter: number) => void;
}) {
  const [view, setView] = useState<View>("vision");
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
  const showIterations = view === "iterations" && multiIter;

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
      {multiIter && (
        <div className="view-toggle" role="tablist" aria-label="Vue du projet">
          <button
            type="button"
            role="tab"
            aria-selected={!showIterations}
            className={!showIterations ? "active" : ""}
            onClick={() => setView("vision")}
          >
            🗂 Vision produit
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={showIterations}
            className={showIterations ? "active" : ""}
            onClick={() => setView("iterations")}
          >
            🕒 Itérations
          </button>
        </div>
      )}
      {showIterations ? (
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
