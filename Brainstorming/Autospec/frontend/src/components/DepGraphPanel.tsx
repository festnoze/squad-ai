import { useMemo } from "react";
import { Stream, UserStory } from "../types";
import {
  blockedBy,
  buildWorkGraph,
  computeGraphLayout,
  WorkItem,
} from "../work";
import { useI18n } from "../i18n/i18n";

interface Props {
  stories: UserStory[];
  streams?: Stream[];
  /** Click a node → open its container story/TS on the board (by story id). */
  onOpenItem?: (storyId: string) => void;
}

const COL = 190; // horizontal spacing between layers (columns)
const ROW = 52; // vertical spacing between nodes of a layer
const NODE_W = 150;
const NODE_H = 34;
const PAD = 16;

/** Visual status of a work item: terminal statuses win; an unstarted item with
 *  unmet deps is "blocked", otherwise "ready". Drives the node colour. */
function nodeState(item: WorkItem, items: Map<string, WorkItem>): string {
  const s = item.status;
  if (s === "done") return "done";
  if (s === "in_progress") return "in_progress";
  if (s === "failed") return "failed";
  if (s === "red") return "red";
  return blockedBy(item.id, items).length > 0 ? "blocked" : "ready";
}

/** Dependency-graph view (the work-item DAG): one node per schedulable item
 *  (task / taskless story / TS task), laid out in topological columns so each
 *  column is a wave of items that can build in parallel; the critical path (the
 *  longest dependency chain) is highlighted. Makes the independence / TS / AND-join
 *  structure visible at a glance. */
export function DepGraphPanel({ stories, streams, onOpenItem }: Props) {
  const { t } = useI18n();
  const technicalIds = useMemo(
    () => new Set((stories ?? []).filter((s) => s.technical).map((s) => s.id)),
    [stories],
  );

  const { items, layout, positions, width, height } = useMemo(() => {
    const items = buildWorkGraph(stories ?? [], streams ?? []);
    const layout = computeGraphLayout(items);
    // Stack nodes within each layer (column), stable by insertion order.
    const perLayerCount = new Map<number, number>();
    const positions = new Map<string, { x: number; y: number }>();
    for (const id of items.keys()) {
      const l = layout.layer.get(id) ?? 0;
      const row = perLayerCount.get(l) ?? 0;
      perLayerCount.set(l, row + 1);
      positions.set(id, { x: PAD + l * COL, y: PAD + row * ROW });
    }
    const width = PAD * 2 + (layout.maxLayer + 1) * COL;
    const height = PAD * 2 + Math.max(1, layout.maxParallel) * ROW;
    return { items, layout, positions, width, height };
  }, [stories, streams]);

  if (items.size === 0) return null;

  const nodes = [...items.values()];
  const edges: { from: string; to: string; crit: boolean }[] = [];
  for (const it of nodes) {
    for (const dep of it.dependsOn) {
      if (!items.has(dep)) continue;
      edges.push({
        from: dep,
        to: it.id,
        crit: layout.critical.has(dep) && layout.critical.has(it.id),
      });
    }
  }

  const open = (it: WorkItem) => onOpenItem?.(it.storyId);

  return (
    <div className="dag-panel">
      <div className="dag-summary" data-testid="dag-summary">
        {t("depGraph.summary", {
          n: items.size,
          waves: layout.maxLayer + 1,
          parallel: layout.maxParallel,
          critical: layout.critical.size,
        })}
      </div>
      <div className="dag-scroll">
        <svg
          className="dag-svg"
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={t("depGraph.title")}
        >
          <defs>
            <marker
              id="dag-arrow"
              viewBox="0 0 8 8"
              refX="7"
              refY="4"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M0,0 L8,4 L0,8 z" fill="#5a6680" />
            </marker>
          </defs>
          {edges.map((e, i) => {
            const a = positions.get(e.from)!;
            const b = positions.get(e.to)!;
            const x1 = a.x + NODE_W;
            const y1 = a.y + NODE_H / 2;
            const x2 = b.x;
            const y2 = b.y + NODE_H / 2;
            const midx = (x1 + x2) / 2;
            return (
              <path
                key={`e-${i}`}
                className={`dag-edge${e.crit ? " dag-edge-crit" : ""}`}
                d={`M${x1},${y1} C${midx},${y1} ${midx},${y2} ${x2},${y2}`}
                markerEnd="url(#dag-arrow)"
                fill="none"
              />
            );
          })}
          {nodes.map((it) => {
            const p = positions.get(it.id)!;
            const st = nodeState(it, items);
            const isTs = technicalIds.has(it.storyId);
            const crit = layout.critical.has(it.id);
            return (
              <g
                key={it.id}
                className={`dag-node dag-node-${st}${crit ? " dag-node-crit" : ""}`}
                transform={`translate(${p.x},${p.y})`}
                onClick={() => open(it)}
                data-testid={`dag-node-${it.id}`}
              >
                <rect width={NODE_W} height={NODE_H} rx={6} />
                <text className="dag-node-id" x={8} y={14}>
                  {isTs ? "🔧 " : ""}
                  {it.id}
                </text>
                <text className="dag-node-title" x={8} y={27}>
                  {(it.title || "").slice(0, 22)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
