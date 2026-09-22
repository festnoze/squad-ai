// Q0 — module-level toast bus, on the same pattern as the i18n store: usable
// from any code (components or plain modules) without prop-drilling. App.tsx
// subscribes once and funnels events into its existing `toasts` state, which
// stays the single rendering point.

/** R6 - optional inline action rendered as a button inside the toast (undo). */
export interface ToastAction {
  label: string;
  onClick: () => void | Promise<void>;
}

export interface ToastEvent {
  level: string;
  title: string;
  body: string;
  /** R6 - when present, the toast renders an action button and lives longer. */
  action?: ToastAction;
}

type Listener = (toast: ToastEvent) => void;

const listeners = new Set<Listener>();

export function subscribeToasts(fn: Listener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/**
 * Emit an in-app toast (levels: "success" | "error" | "info").
 * `action` is optional; when given, the toast shows a button (R6 undo).
 */
export function notify(
  level: string,
  title: string,
  body = "",
  action?: ToastAction,
): void {
  for (const fn of listeners) fn(action ? { level, title, body, action } : { level, title, body });
}
