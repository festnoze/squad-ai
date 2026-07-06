// Q0 — module-level toast bus, on the same pattern as the i18n store: usable
// from any code (components or plain modules) without prop-drilling. App.tsx
// subscribes once and funnels events into its existing `toasts` state, which
// stays the single rendering point.

export interface ToastEvent {
  level: string;
  title: string;
  body: string;
}

type Listener = (toast: ToastEvent) => void;

const listeners = new Set<Listener>();

export function subscribeToasts(fn: Listener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** Emit an in-app toast (levels: "success" | "error" | "info"). */
export function notify(level: string, title: string, body = ""): void {
  for (const fn of listeners) fn({ level, title, body });
}
