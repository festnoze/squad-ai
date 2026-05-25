// Epic 4: simple polling hook that refreshes a project's items at a fixed
// interval. Used by UserStoriesView / TasksView to see mock execution
// transitions (in_progress -> in_test -> done) appear in real time.
//
// Kept deliberately minimal: no global store, no websocket, no retries.

import { useEffect, useRef } from 'react';
import type { Item, ItemType } from '../types/chat';
import { listProjectItems } from '../api/items';

interface UseItemsPollingOptions {
  projectId: string | undefined;
  typeFilter: ItemType | undefined;
  enabled: boolean;
  intervalMs?: number;
  onItems: (items: Item[]) => void;
  onError?: (error: Error) => void;
}

export function useItemsPolling(options: UseItemsPollingOptions): void {
  const {
    projectId,
    typeFilter,
    enabled,
    intervalMs = 2000,
    onItems,
    onError,
  } = options;

  // Keep callbacks in refs so the effect doesn't re-run on every parent
  // render (the parent typically passes fresh closures every time).
  const onItemsRef = useRef(onItems);
  const onErrorRef = useRef(onError);
  onItemsRef.current = onItems;
  onErrorRef.current = onError;

  useEffect(() => {
    if (!enabled || !projectId) {
      return;
    }

    let cancelled = false;

    async function atick(): Promise<void> {
      try {
        const items = await listProjectItems(projectId!, typeFilter);
        if (cancelled) return;
        onItemsRef.current(items);
      } catch (err) {
        if (cancelled) return;
        if (onErrorRef.current) {
          onErrorRef.current(
            err instanceof Error ? err : new Error(String(err)),
          );
        }
        // Don't stop polling on transient errors: the next tick will retry.
      }
    }

    // Immediate first tick, then periodic.
    void atick();
    const intervalId = window.setInterval(() => {
      void atick();
    }, intervalMs);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [projectId, typeFilter, enabled, intervalMs]);
}
