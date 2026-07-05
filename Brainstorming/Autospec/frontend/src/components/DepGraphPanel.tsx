import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  applyNodeChanges,
  type Edge,
  type Node,
  type NodeChange,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Epic, Stream, UserStory } from "../types";
import { computeDagView, DagViewNode, ITEM_H, ITEM_W } from "../graph";
import { t, useI18n } from "../i18n/i18n";

interface Props {
  epics: Epic[];
  stories: UserStory[];
  streams?: Stream[];
  /** Double-click a story/task → open its container story/TS on the board. */
  onOpenItem?: (storyId: string) => void;
  /** Double-click an epic → open the epic on the board. */
  onOpenEpic?: (epicId: string) => void;
}

/** Data payload carried by every graph node (spec + interaction callbacks). */
type DagData = DagViewNode & {
  onToggle: (id: string) => void;
  onFocus: (id: string) => void;
};

const KIND_ICON: Record<string, string> = {
  epic: "📦",
  story: "",
  ts: "🔧",
  task: "",
};

function stop(e: React.MouseEvent) {
  e.stopPropagation();
}

/** Card node: a leaf (task / taskless US), a collapsed container, or a ghost. */
function DagItemNode({ data }: NodeProps) {
  const d = data as unknown as DagData;
  return (
    <div
      className={`dag-item dag-state-${d.state}${d.ghost ? " dag-ghost" : ""}${d.crit ? " dag-crit" : ""} dag-kind-${d.kind}`}
      data-testid={`dag-node-${d.id}`}
    >
      <Handle type="target" position={Position.Left} className="dag-handle" />
      <div className="dag-item-head">
        {d.container && !d.ghost && (
          <button
            type="button"
            className="dag-btn nodrag"
            title={t("depGraph.expand")}
            data-testid={`dag-toggle-${d.id}`}
            onClick={(e) => {
              stop(e);
              d.onToggle(d.id);
            }}
            onDoubleClick={stop}
          >
            ▸
          </button>
        )}
        <span className="dag-item-id">
          {KIND_ICON[d.kind] ? `${KIND_ICON[d.kind]} ` : ""}
          {d.id}
        </span>
        {d.container && <span className="dag-count">{d.childCount}</span>}
        {d.kind !== "task" && (
          <button
            type="button"
            className="dag-btn nodrag"
            title={t("depGraph.focus")}
            data-testid={`dag-focus-${d.id}`}
            onClick={(e) => {
              stop(e);
              d.onFocus(d.id);
            }}
            onDoubleClick={stop}
          >
            ◎
          </button>
        )}
      </div>
      <div className="dag-item-title">{d.title}</div>
      <Handle type="source" position={Position.Right} className="dag-handle" />
    </div>
  );
}

/** Expanded container box (epic or decomposed US/TS) holding its children. */
function DagGroupNode({ data }: NodeProps) {
  const d = data as unknown as DagData;
  return (
    <div
      className={`dag-group dag-state-${d.state} dag-kind-${d.kind}`}
      data-testid={`dag-group-${d.id}`}
    >
      <div className="dag-group-head">
        <button
          type="button"
          className="dag-btn nodrag"
          title={t("depGraph.collapse")}
          data-testid={`dag-toggle-${d.id}`}
          onClick={(e) => {
            stop(e);
            d.onToggle(d.id);
          }}
          onDoubleClick={stop}
        >
          ▾
        </button>
        <span className="dag-item-id">
          {KIND_ICON[d.kind] ? `${KIND_ICON[d.kind]} ` : ""}
          {d.id}
        </span>
        <span className="dag-group-title">{d.title}</span>
        <span className="dag-count">{d.childCount}</span>
        <button
          type="button"
          className="dag-btn nodrag"
          title={t("depGraph.focus")}
          data-testid={`dag-focus-${d.id}`}
          onClick={(e) => {
            stop(e);
            d.onFocus(d.id);
          }}
          onDoubleClick={stop}
        >
          ◎
        </button>
      </div>
    </div>
  );
}

const nodeTypes = { dagItem: DagItemNode, dagGroup: DagGroupNode };

/** Dependency-graph tab, hierarchical edition: epics → US/TS → tasks rendered
 *  with React Flow. Everything is collapsed by default; each level opens in
 *  place (dagre re-layouts automatically), any epic/US can be focused alone,
 *  nodes stay draggable (edges follow) and the canvas grows with real
 *  scrollbars instead of pan/zoom. */
export function DepGraphPanel({
  epics,
  stories,
  streams,
  onOpenItem,
  onOpenEpic,
}: Props) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [focusId, setFocusId] = useState<string | null>(null);

  const view = useMemo(
    () =>
      computeDagView(epics ?? [], stories ?? [], streams ?? [], expanded, focusId),
    [epics, stories, streams, expanded, focusId],
  );

  const toggle = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);
  const focus = useCallback((id: string) => setFocusId(id), []);

  // Layouted specs → React Flow nodes. Recomputed on every structural change
  // (expand/collapse/focus/data), which resets manual drag offsets — that's the
  // "auto-adapt" behaviour: the layout always reflects the current level.
  const layoutNodes = useMemo<Node[]>(
    () =>
      view.nodes.map((spec) => ({
        id: spec.id,
        type: spec.type === "group" ? "dagGroup" : "dagItem",
        position: { x: spec.x, y: spec.y },
        parentId: spec.parentId,
        extent: spec.parentId ? ("parent" as const) : undefined,
        style: { width: spec.w, height: spec.h },
        data: { ...spec, onToggle: toggle, onFocus: focus },
      })),
    [view, toggle, focus],
  );

  const [nodes, setNodes] = useState<Node[]>(layoutNodes);
  useEffect(() => setNodes(layoutNodes), [layoutNodes]);

  // Free drag for top-level nodes (clamped to ≥0 so nothing escapes the
  // scrollable canvas); children are constrained to their parent group.
  const onNodesChange = useCallback((changes: NodeChange[]) => {
    setNodes((ns) =>
      applyNodeChanges(changes, ns).map((n) =>
        n.parentId
          ? n
          : {
              ...n,
              position: {
                x: Math.max(0, n.position.x),
                y: Math.max(0, n.position.y),
              },
            },
      ),
    );
  }, []);

  const rfEdges = useMemo<Edge[]>(
    () =>
      view.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        className: e.crit ? "dag-edge dag-edge-crit" : "dag-edge",
        markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
      })),
    [view],
  );

  const onNodeDoubleClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const d = node.data as unknown as DagData;
      if (d.kind === "epic") onOpenEpic?.(d.id);
      else onOpenItem?.(d.storyId || d.id);
    },
    [onOpenEpic, onOpenItem],
  );

  // The canvas grows with the layout AND with manual drags, so the wrapper's
  // native scrollbars always cover the content (zoom/pan are disabled).
  const canvas = useMemo(() => {
    let w = view.width;
    let h = view.height;
    for (const n of nodes) {
      if (n.parentId) continue;
      w = Math.max(w, n.position.x + (Number(n.style?.width) || ITEM_W) + 24);
      h = Math.max(h, n.position.y + (Number(n.style?.height) || ITEM_H) + 24);
    }
    return { w, h };
  }, [nodes, view.width, view.height]);

  if (view.summary.n === 0) return null;

  return (
    <div className="dag-panel">
      <div className="dag-toolbar">
        {view.focusPath.length > 0 && (
          <>
            <button
              type="button"
              className="dag-tool"
              data-testid="dag-back"
              onClick={() => setFocusId(null)}
            >
              ⌂ {t("depGraph.backToProject")}
            </button>
            {view.focusPath.map((p, i) => (
              <span key={p.id} className="dag-crumb-wrap">
                <span className="dag-crumb-sep">›</span>
                <button
                  type="button"
                  className="dag-crumb"
                  onClick={() => setFocusId(p.id)}
                  disabled={i === view.focusPath.length - 1}
                >
                  {p.id}
                </button>
              </span>
            ))}
          </>
        )}
        <span className="dag-summary" data-testid="dag-summary">
          {t("depGraph.summary", view.summary)}
        </span>
        <span className="dag-spacer" />
        <button
          type="button"
          className="dag-tool"
          data-testid="dag-expand-all"
          onClick={() => setExpanded(new Set(view.containerIds))}
        >
          {t("depGraph.expandAll")}
        </button>
        <button
          type="button"
          className="dag-tool"
          data-testid="dag-collapse-all"
          onClick={() => setExpanded(new Set())}
        >
          {t("depGraph.collapseAll")}
        </button>
      </div>
      <div className="dag-hint">{t("depGraph.hint")}</div>
      <div className="dag-scroll" data-testid="dag-scroll">
        <div
          className="dag-canvas"
          style={{ width: canvas.w, height: canvas.h }}
        >
          <ReactFlow
            nodes={nodes}
            edges={rfEdges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onNodeDoubleClick={onNodeDoubleClick}
            minZoom={1}
            maxZoom={1}
            defaultViewport={{ x: 0, y: 0, zoom: 1 }}
            panOnDrag={false}
            panOnScroll={false}
            zoomOnScroll={false}
            zoomOnPinch={false}
            zoomOnDoubleClick={false}
            preventScrolling={false}
            nodesConnectable={false}
            deleteKeyCode={null}
            selectNodesOnDrag={false}
            aria-label={t("depGraph.title")}
          >
            <Background variant={BackgroundVariant.Dots} gap={24} size={1} />
          </ReactFlow>
        </div>
      </div>
    </div>
  );
}
