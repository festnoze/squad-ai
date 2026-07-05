// Hierarchical model behind the "Graphe" tab: builds the epic → US/TS → task
// tree, lifts leaf-level dependencies (from work.ts's buildWorkGraph) to the
// currently visible level (collapse / expand / focus), and lays everything out
// with dagre. Pure and React-free so it stays unit-testable; DepGraphPanel only
// maps the resulting specs onto React Flow nodes/edges.

import dagre from "@dagrejs/dagre";
import { Epic, Stream, UserStory } from "./types";
import { blockedBy, buildWorkGraph, computeGraphLayout, WorkItem } from "./work";

export type DagKind = "epic" | "story" | "ts" | "task";

/** Fixed size of a collapsed/leaf card; expanded groups are sized by dagre. */
export const ITEM_W = 200;
export const ITEM_H = 52;
const GROUP_HEADER = 34; // room for the group's title bar above its children
const LEVEL_MARGIN = 16; // dagre margin inside each level (and around the root)
const NODESEP = 18;
const RANKSEP = 64;

interface TreeNode {
  id: string;
  kind: DagKind;
  title: string;
  /** Owning story id for board navigation ("" for epics). */
  storyId: string;
  epicId: string;
  children: TreeNode[];
}

/** One node spec for the view: either a card ("item": leaf, collapsed container
 *  or out-of-focus ghost) or an expanded container box ("group"). Positions are
 *  relative to `parentId` (React Flow convention), absolute at top level. */
export interface DagViewNode {
  id: string;
  parentId?: string;
  x: number;
  y: number;
  w: number;
  h: number;
  type: "item" | "group";
  kind: DagKind;
  title: string;
  /** Visual state: done | in_progress | failed | red | blocked | ready. */
  state: string;
  storyId: string;
  epicId: string;
  /** Out-of-focus neighbour shown dimmed for context (focus mode only). */
  ghost: boolean;
  container: boolean;
  expanded: boolean;
  childCount: number;
  /** Leaf work item on the critical path. */
  crit: boolean;
}

export interface DagViewEdge {
  id: string;
  source: string;
  target: string;
  crit: boolean;
}

export interface DagView {
  nodes: DagViewNode[];
  edges: DagViewEdge[];
  width: number;
  height: number;
  /** Every collapsible container id (for "expand all"). */
  containerIds: string[];
  /** Project-wide DAG stats (independent of collapse/focus). */
  summary: { n: number; waves: number; parallel: number; critical: number };
  /** Breadcrumb of the focused node (empty = project view / unknown focus). */
  focusPath: { id: string; kind: DagKind; title: string }[];
}

/** Visual state of a leaf work item: terminal statuses win; an unstarted item
 *  with unmet deps is "blocked", otherwise "ready". */
function leafState(item: WorkItem, items: Map<string, WorkItem>): string {
  const s = item.status;
  if (s === "done") return "done";
  if (s === "in_progress") return "in_progress";
  if (s === "failed") return "failed";
  if (s === "red") return "red";
  return blockedBy(item.id, items).length > 0 ? "blocked" : "ready";
}

/** Aggregate state of a container from its leaf work items (mirrors the spirit
 *  of usEffectiveStatus, plus the blocked/ready split for untouched subtrees). */
function containerState(
  node: TreeNode,
  items: Map<string, WorkItem>,
): string {
  const leaves: WorkItem[] = [];
  const walk = (n: TreeNode) => {
    const it = items.get(n.id);
    if (it) leaves.push(it);
    n.children.forEach(walk);
  };
  walk(node);
  if (leaves.length === 0) return "ready";
  if (leaves.every((l) => l.status === "done")) return "done";
  if (leaves.some((l) => ["in_progress", "red", "green"].includes(l.status)))
    return "in_progress";
  if (leaves.some((l) => l.status === "failed")) return "failed";
  return leaves.some((l) => leafState(l, items) === "ready") ? "ready" : "blocked";
}

/** Build the epic → US/TS → task tree. A TS nests under its parent story when
 *  known, else under its epic; stories referencing an unknown epic get a
 *  synthetic epic node so nothing is dropped. */
function buildTree(
  epics: Epic[],
  stories: UserStory[],
): { roots: TreeNode[]; byId: Map<string, TreeNode>; parentOf: Map<string, string> } {
  const storyById = new Map(stories.map((s) => [s.id, s]));
  const childTs = new Map<string, UserStory[]>();
  const byEpic = new Map<string, UserStory[]>();
  for (const s of stories) {
    if (s.parent_id && storyById.has(s.parent_id)) {
      const arr = childTs.get(s.parent_id) ?? [];
      arr.push(s);
      childTs.set(s.parent_id, arr);
    } else {
      const eid = s.epic_id || "epic";
      const arr = byEpic.get(eid) ?? [];
      arr.push(s);
      byEpic.set(eid, arr);
    }
  }

  const byId = new Map<string, TreeNode>();
  const parentOf = new Map<string, string>();

  const storyNode = (s: UserStory, epicId: string): TreeNode => {
    const node: TreeNode = {
      id: s.id,
      kind: s.technical ? "ts" : "story",
      title: s.title || s.id,
      storyId: s.id,
      epicId,
      children: [],
    };
    for (const t of s.tasks ?? []) {
      const child: TreeNode = {
        id: t.id,
        kind: "task",
        title: t.title || t.id,
        storyId: s.id,
        epicId,
        children: [],
      };
      node.children.push(child);
      byId.set(child.id, child);
      parentOf.set(child.id, s.id);
    }
    for (const ts of childTs.get(s.id) ?? []) {
      const child = storyNode(ts, epicId);
      node.children.push(child);
      parentOf.set(child.id, s.id);
    }
    byId.set(s.id, node);
    return node;
  };

  const roots: TreeNode[] = [];
  const seenEpics = new Set<string>();
  const addEpic = (id: string, title: string) => {
    const list = byEpic.get(id);
    if (!list || seenEpics.has(id)) return;
    seenEpics.add(id);
    const node: TreeNode = {
      id,
      kind: "epic",
      title,
      storyId: "",
      epicId: id,
      children: [],
    };
    for (const s of list) {
      const child = storyNode(s, id);
      node.children.push(child);
      parentOf.set(child.id, id);
    }
    byId.set(id, node);
    roots.push(node);
  };
  for (const e of epics) addEpic(e.id, e.title || e.id);
  for (const eid of byEpic.keys()) addEpic(eid, eid); // orphans → synthetic epic
  return { roots, byId, parentOf };
}

/** Dagre-layout one level (the direct children of a container, or the top
 *  level). Mutates each child spec's x/y; returns the level's extent. */
function layoutLevel(
  children: { id: string; w: number; h: number; self: DagViewNode }[],
  edges: [string, string][],
): { w: number; h: number } {
  const g = new dagre.graphlib.Graph();
  g.setGraph({
    rankdir: "LR",
    nodesep: NODESEP,
    ranksep: RANKSEP,
    marginx: LEVEL_MARGIN,
    marginy: LEVEL_MARGIN,
  });
  g.setDefaultEdgeLabel(() => ({}));
  for (const c of children) g.setNode(c.id, { width: c.w, height: c.h });
  for (const [a, b] of edges) {
    if (g.hasNode(a) && g.hasNode(b) && a !== b) g.setEdge(a, b);
  }
  dagre.layout(g);
  let w = 0;
  let h = 0;
  for (const c of children) {
    const p = g.node(c.id);
    c.self.x = p.x - c.w / 2;
    c.self.y = p.y - c.h / 2;
    w = Math.max(w, c.self.x + c.w);
    h = Math.max(h, c.self.y + c.h);
  }
  return { w: w + LEVEL_MARGIN, h: h + LEVEL_MARGIN };
}

/** Compute the full view for the current collapse/focus state. */
export function computeDagView(
  epics: Epic[],
  stories: UserStory[],
  streams: Stream[],
  expanded: ReadonlySet<string>,
  focusId: string | null,
): DagView {
  const items = buildWorkGraph(stories, streams);
  const layout = computeGraphLayout(items);
  const summary = {
    n: items.size,
    waves: layout.maxLayer + 1,
    parallel: layout.maxParallel,
    critical: layout.critical.size,
  };
  const { roots, byId, parentOf } = buildTree(epics, stories);
  const focus = focusId && byId.has(focusId) ? focusId : null;

  const effExpanded = new Set(expanded);
  if (focus) effExpanded.add(focus); // the focused element is always open

  const isExpanded = (n: TreeNode) =>
    n.children.length > 0 && effExpanded.has(n.id);

  const treePath = (id: string): string[] => {
    const path: string[] = [];
    let cur: string | undefined = id;
    while (cur) {
      path.unshift(cur);
      cur = parentOf.get(cur);
    }
    return path;
  };

  /** Visible representative of a leaf work item: its first non-expanded
   *  ancestor (walking down from the render root), or the leaf itself. Items
   *  outside the focused subtree collapse to their owning story as a ghost. */
  const repOf = (itemId: string): { id: string; ghost: boolean } => {
    const path = treePath(itemId);
    let start = 0;
    if (focus) {
      const i = path.indexOf(focus);
      if (i < 0) {
        const it = items.get(itemId);
        return { id: it?.storyId || itemId, ghost: true };
      }
      start = i;
    }
    for (let j = start; j < path.length - 1; j++) {
      const n = byId.get(path[j]);
      if (n && !isExpanded(n)) return { id: n.id, ghost: false };
    }
    return { id: itemId, ghost: false };
  };

  // --- Aggregate leaf dependencies to their visible representatives. ---------
  const agg = new Map<string, DagViewEdge>();
  const ghostIds = new Set<string>();
  for (const it of items.values()) {
    for (const dep of it.dependsOn) {
      if (!items.has(dep)) continue;
      const a = repOf(dep);
      const b = repOf(it.id);
      if (a.id === b.id) continue; // internal to one visible node
      if (a.ghost && b.ghost) continue; // fully outside the focus
      if (a.ghost) ghostIds.add(a.id);
      if (b.ghost) ghostIds.add(b.id);
      const key = `${a.id}->${b.id}`;
      const crit =
        a.id === dep &&
        b.id === it.id &&
        layout.critical.has(dep) &&
        layout.critical.has(it.id);
      const prev = agg.get(key);
      if (prev) prev.crit = prev.crit || crit;
      else agg.set(key, { id: key, source: a.id, target: b.id, crit });
    }
  }
  const edges = [...agg.values()];

  // --- Lift each visible edge to the level (container) where it constrains the
  // dagre layout: the lowest common ancestor of its two endpoints ("" = root).
  const displayPath = (repId: string, ghost: boolean): string[] => {
    if (ghost) return [repId];
    const path = treePath(repId);
    if (focus) return path.slice(path.indexOf(focus));
    return path;
  };
  const lifted = new Map<string, [string, string][]>();
  for (const e of edges) {
    const pa = displayPath(e.source, ghostIds.has(e.source));
    const pb = displayPath(e.target, ghostIds.has(e.target));
    let k = 0;
    while (k < pa.length && k < pb.length && pa[k] === pb[k]) k++;
    if (k >= pa.length || k >= pb.length) continue; // one contains the other
    const level = k === 0 ? "" : pa[k - 1];
    const arr = lifted.get(level) ?? [];
    arr.push([pa[k], pb[k]]);
    lifted.set(level, arr);
  }

  // --- Recursive layout: children first (to know expanded-group sizes), then
  // dagre at each level; child positions are relative to their group.
  interface Sub {
    id: string;
    w: number;
    h: number;
    self: DagViewNode;
    desc: DagViewNode[];
  }

  const makeSpec = (n: TreeNode, ghost: boolean): DagViewNode => ({
    id: n.id,
    x: 0,
    y: 0,
    w: ITEM_W,
    h: ITEM_H,
    type: "item",
    kind: n.kind,
    title: n.title,
    state: items.has(n.id)
      ? leafState(items.get(n.id)!, items)
      : containerState(n, items),
    storyId: n.storyId,
    epicId: n.epicId,
    ghost,
    container: n.children.length > 0,
    expanded: false,
    childCount: n.children.length,
    crit: !ghost && items.has(n.id) && layout.critical.has(n.id),
  });

  const buildSub = (n: TreeNode): Sub => {
    const self = makeSpec(n, false);
    if (!isExpanded(n)) return { id: n.id, w: self.w, h: self.h, self, desc: [] };
    const subs = n.children.map(buildSub);
    for (const s of subs) s.self.parentId = n.id;
    const { w, h } = layoutLevel(subs, lifted.get(n.id) ?? []);
    for (const s of subs) s.self.y += GROUP_HEADER;
    self.type = "group";
    self.expanded = true;
    self.w = Math.max(w, ITEM_W);
    self.h = h + GROUP_HEADER;
    return {
      id: n.id,
      w: self.w,
      h: self.h,
      self,
      desc: subs.flatMap((s) => [s.self, ...s.desc]),
    };
  };

  const topSubs = (focus ? [byId.get(focus)!] : roots).map(buildSub);
  for (const gid of ghostIds) {
    const n = byId.get(gid);
    if (!n) continue;
    const spec = makeSpec(n, true);
    topSubs.push({ id: gid, w: spec.w, h: spec.h, self: spec, desc: [] });
  }
  const { w, h } = layoutLevel(topSubs, lifted.get("") ?? []);
  const nodes = topSubs.flatMap((s) => [s.self, ...s.desc]);

  const containerIds = [...byId.values()]
    .filter((n) => n.children.length > 0)
    .map((n) => n.id);

  const focusPath = focus
    ? treePath(focus).map((id) => {
        const n = byId.get(id)!;
        return { id: n.id, kind: n.kind, title: n.title };
      })
    : [];

  return { nodes, edges, width: w, height: h, containerIds, summary, focusPath };
}
