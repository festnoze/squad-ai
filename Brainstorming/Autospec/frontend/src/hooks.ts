import { useEffect, useRef } from "react";

// Q1 — shared Escape-to-close behavior for modals, overlays and popovers.
// A module-level LIFO stack guarantees that stacked overlays close from the
// innermost out (the ConfirmDialog above a diff overlay closes first): only
// the most recently mounted active handler consumes the key.
const escapeStack: (() => void)[] = [];

function onDocumentKeydown(e: KeyboardEvent) {
  if (e.key !== "Escape" || e.defaultPrevented || escapeStack.length === 0) return;
  e.preventDefault();
  escapeStack[escapeStack.length - 1]();
}

let bound = false;

export function useEscapeToClose(active: boolean, onClose: () => void): void {
  // Ref so re-renders with a fresh closure don't re-order the stack.
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    if (!active) return;
    const handler = () => closeRef.current();
    escapeStack.push(handler);
    if (!bound) {
      document.addEventListener("keydown", onDocumentKeydown);
      bound = true;
    }
    return () => {
      const i = escapeStack.indexOf(handler);
      if (i >= 0) escapeStack.splice(i, 1);
    };
  }, [active]);
}
