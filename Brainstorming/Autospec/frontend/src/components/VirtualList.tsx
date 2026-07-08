import { ReactNode, useEffect, useRef, useState } from "react";

// R1 — threshold-gated windowing. A pure slice helper keeps the math testable
// without faking jsdom layout; the component renders EVERYTHING below the
// threshold (so small lists — and every existing test — are byte-for-byte
// unchanged) and only windows genuinely large lists.

export interface WindowSlice {
  start: number;
  end: number;
  padTop: number;
  padBottom: number;
}

/** Compute the visible slice + spacer heights for a fixed-row-height window. */
export function windowSlice(
  count: number,
  scrollTop: number,
  viewport: number,
  itemHeight: number,
  overscan: number,
): WindowSlice {
  const start = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan);
  const visible = Math.ceil(viewport / itemHeight) + overscan * 2;
  const end = Math.min(count, start + visible);
  return { start, end, padTop: start * itemHeight, padBottom: (count - end) * itemHeight };
}

interface Props<T> {
  items: T[];
  /** Estimated row height (px). Only used when windowing kicks in. */
  itemHeight: number;
  renderItem: (item: T, index: number) => ReactNode;
  className?: string;
  overscan?: number;
  /** Below this count the whole list is rendered (default 60). */
  threshold?: number;
  /** Logs: keep pinned to the newest row when new items arrive. */
  stickBottom?: boolean;
  testid?: string;
}

/**
 * A minimal fixed-height virtual list. Windows only when `items.length >
 * threshold` AND the container has a measurable height (so jsdom — clientHeight
 * 0 — always takes the render-all path). Rows are assumed ~`itemHeight` tall;
 * an occasionally-taller row (e.g. an expanded drawer) causes minor drift below
 * it, an accepted trade-off vs. rendering thousands of nodes.
 */
export function VirtualList<T>({
  items,
  itemHeight,
  renderItem,
  className,
  overscan = 6,
  threshold = 60,
  stickBottom = false,
  testid,
}: Props<T>) {
  const ref = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewport, setViewport] = useState(0);
  // Whether the user is pinned to the bottom (for stickBottom logs).
  const atBottom = useRef(true);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setViewport(el.clientHeight);
    const onScroll = () => {
      setScrollTop(el.scrollTop);
      atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    };
    measure();
    el.addEventListener("scroll", onScroll);
    window.addEventListener("resize", measure);
    return () => {
      el.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", measure);
    };
  }, []);

  // stickBottom: when new rows arrive and the user was at the bottom, follow.
  useEffect(() => {
    const el = ref.current;
    if (el && stickBottom && atBottom.current) el.scrollTop = el.scrollHeight;
  }, [items.length, stickBottom]);

  const windowing = items.length > threshold && viewport > 0;

  if (!windowing) {
    return (
      <div ref={ref} className={className} data-testid={testid}>
        {items.map((it, i) => renderItem(it, i))}
      </div>
    );
  }

  const { start, end, padTop, padBottom } = windowSlice(
    items.length,
    scrollTop,
    viewport,
    itemHeight,
    overscan,
  );
  return (
    <div ref={ref} className={className} data-testid={testid}>
      {/* flexShrink:0 so the spacers keep their height inside a flex-column list. */}
      <div style={{ height: padTop, flexShrink: 0 }} aria-hidden="true" />
      {items.slice(start, end).map((it, i) => renderItem(it, start + i))}
      <div style={{ height: padBottom, flexShrink: 0 }} aria-hidden="true" />
    </div>
  );
}
