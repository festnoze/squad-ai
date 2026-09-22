import { useEffect, useMemo, useRef, useState } from "react";
import { getIterations } from "../api";
import { subscribeNav, type NavIntent } from "../navigation";
import { Epic, ProjectTicks, Stream, TrashedStoryInfo, Usage, UserStory } from "../types";
import { useI18n } from "../i18n/i18n";
import { Activity } from "./Activity";
import { Board } from "./Board";
import { IterationsView } from "./IterationsView";
import { DepGraphPanel } from "./DepGraphPanel";

type View = "vision" | "iterations" | "activity" | "graph";

const VIEWS: readonly View[] = ["vision", "iterations", "activity", "graph"];

/** R3: per-project localStorage key holding the last EXPLICIT tab choice. */
const viewKey = (projectId: string) => `autospec-view:${projectId}`;

/** Read the remembered tab for a project (null when absent/invalid/unavailable). */
function readStoredView(projectId: string): View | null {
  try {
    const raw = localStorage.getItem(viewKey(projectId));
    return VIEWS.includes(raw as View) ? (raw as View) : null;
  } catch {
    return null; // private mode / storage disabled
  }
}

/** Persist an explicit tab choice; never throws. */
function storeView(projectId: string, view: View): void {
  try {
    localStorage.setItem(viewKey(projectId), view);
  } catch {
    /* storage unavailable: the choice simply is not remembered */
  }
}

/**
 * R3: has this project ever entered (or is it in) a build? True when the phase
 * is BUILD, or when any story/task left the initial state - a stage other than
 * "queued", or a status other than "todo". A project still in spec/plan has
 * nothing to show in the Activity lens, so it stays on the product vision.
 */
export function hasBuildActivity(phase: string | undefined, stories: UserStory[]): boolean {
  if (phase === "build") return true;
  const moved = (status: string | undefined, stage: string | undefined) =>
    (status ?? "todo") !== "todo" || (stage ?? "queued") !== "queued";
  return (stories ?? []).some(
    (s) =>
      moved(s.status, s.current_stage) ||
      (s.tasks ?? []).some((t) => moved(t.status, t.current_stage)),
  );
}

/** Initial lens: the remembered explicit choice wins, else the R3 default. */
function initialView(projectId: string, phase: string | undefined, stories: UserStory[]): View {
  return readStoredView(projectId) ?? (hasBuildActivity(phase, stories) ? "activity" : "vision");
}

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
  trash,
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
  /** R6: soft-deleted stories, forwarded to the Board trash panel. */
  trash?: TrashedStoryInfo[];
}) {
  const { t } = useI18n();
  // P6/B-UX/R3: Activité is the default lens as soon as a build has started or
  // happened; Board + Iterations stay available. A project still in spec/plan
  // keeps the historic "vision produit" default. An explicit tab click is
  // remembered per project and wins over that default on mount.
  const [view, setView] = useState<View>(() => initialView(projectId, phase, stories));
  // True once the user picked a tab for THIS project (seeded from storage): it
  // freezes the automatic switch on the BUILD transition.
  const userPicked = useRef<boolean>(readStoredView(projectId) !== null);
  const prevPhase = useRef<string | undefined>(phase);
  const lastProject = useRef<string>(projectId);
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
  // The dependency-graph tab is useful once there's actual structure (tasks or
  // declared dependencies); a flat list of independent US has nothing to show.
  const hasGraph = useMemo(
    () =>
      (stories ?? []).some(
        (s) => (s.tasks ?? []).length > 0 || (s.depends_on ?? []).length > 0,
      ),
    [stories],
  );
  const showGraph = view === "graph" && hasGraph;

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

  // R3: the component is not keyed by project in App, so switching projects
  // re-runs the initial-lens decision (and re-seeds the per-project memory).
  useEffect(() => {
    if (lastProject.current === projectId) return;
    lastProject.current = projectId;
    prevPhase.current = phase;
    userPicked.current = readStoredView(projectId) !== null;
    setView(initialView(projectId, phase, stories));
  }, [projectId, phase, stories]);

  // R3: when the phase ENTERS build while the user is on another lens, switch
  // to Activité once. An explicit tab choice for this project disables it.
  useEffect(() => {
    const was = prevPhase.current;
    prevPhase.current = phase;
    if (phase !== "build" || was === "build") return;
    if (userPicked.current) return;
    setView("activity");
  }, [phase]);

  /** Explicit tab click: switch lens AND remember it for this project. */
  const selectView = (next: View) => {
    userPicked.current = true;
    storeView(projectId, next);
    setView(next);
  };

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
  // Graph node → open its container story/TS on the board (find its epic first).
  const openWorkItemStory = (storyId: string) => {
    const s = stories.find((x) => x.id === storyId);
    if (s) openStory(s.epic_id, s.id);
  };

  // R2 — the command palette drives navigation through a module-level bus. A ref
  // holds the latest handler so we subscribe ONCE (stable) yet always see the
  // current `stories`/view setters (avoids stale closures + resubscribe churn).
  const navHandler = useRef<(intent: NavIntent) => void>(() => undefined);
  navHandler.current = (intent) => {
    if (intent.type === "view") {
      if (intent.view === "graph" && !hasGraph) return;
      if (intent.view === "iterations" && !multiIter) return;
      setView(intent.view);
    } else if (intent.type === "goto-item") {
      const item = stories.find(
        (x) => x.id === intent.storyId || (x.tasks ?? []).some((tk) => tk.id === intent.storyId),
      );
      if (item) openStory(item.epic_id, item.id);
    }
  };
  useEffect(() => subscribeNav((intent) => navHandler.current(intent)), []);

  return (
    <>
      <div className="view-toggle" role="tablist" aria-label={t("workspaceViews.projectView")}>
        <button
          type="button"
          role="tab"
          aria-selected={showActivity}
          className={showActivity ? "active" : ""}
          onClick={() => selectView("activity")}
        >
          {t("workspaceViews.activity")}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={!showActivity && !showIterations && !showGraph}
          className={!showActivity && !showIterations && !showGraph ? "active" : ""}
          onClick={() => selectView("vision")}
        >
          {t("workspaceViews.productVision")}
        </button>
        {hasGraph && (
          <button
            type="button"
            role="tab"
            aria-selected={showGraph}
            className={showGraph ? "active" : ""}
            onClick={() => selectView("graph")}
          >
            {t("workspaceViews.graph")}
          </button>
        )}
        {multiIter && (
          <button
            type="button"
            role="tab"
            aria-selected={showIterations}
            className={showIterations ? "active" : ""}
            onClick={() => selectView("iterations")}
          >
            {t("workspaceViews.iterations")}
          </button>
        )}
      </div>
      {showGraph ? (
        <DepGraphPanel
          epics={epics}
          stories={stories}
          streams={streams}
          onOpenItem={openWorkItemStory}
          onOpenEpic={openEpic}
        />
      ) : showActivity ? (
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
          trash={trash}
        />
      )}
    </>
  );
}
