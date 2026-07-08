// R2 — module-level navigation intent bus (same pattern as toast.ts / the
// ConfirmDialog service). Lets the global command palette drive the workspace
// navigation (view switch / jump to an item) without lifting WorkspaceViews'
// local view+focus state up to App. WorkspaceViews subscribes; the palette (and
// anything else) dispatches.

export type WorkspaceView = "activity" | "vision" | "graph" | "iterations";

export type NavIntent =
  | { type: "view"; view: WorkspaceView }
  | { type: "goto-item"; storyId: string };

const listeners = new Set<(intent: NavIntent) => void>();

export function subscribeNav(fn: (intent: NavIntent) => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function dispatchNav(intent: NavIntent): void {
  for (const fn of listeners) fn(intent);
}
