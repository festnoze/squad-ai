// Live project journal: server-sent events first, index-based polling as the fallback.
import { useEffect, useRef, useState } from "react";
import { ApiError, getEvents, streamUrl, type ProjectEvent } from "./api";

export type StreamMode = "connecting" | "live" | "polling" | "paused" | "gone";

export const MAX_EVENTS = 2000; // keep the browser responsive on very long runs
export const DEFAULT_POLL_MS = 2000;

export interface UseEventsOptions {
  pollMs?: number;
  /** Called with every batch of new events (after deduplication). */
  onEvents?: (events: ProjectEvent[]) => void;
  /** Called once when the server no longer knows the project (404): polling stops. */
  onGone?: () => void;
}

const isHidden = () => typeof document !== "undefined" && document.visibilityState === "hidden";

/**
 * Streams the events of one project. The cursor is the index of the next expected event,
 * so a switch from the stream to polling (`/events?after=<cursor>`) or a reconnection
 * (`/stream?after=<cursor>`) neither skips nor repeats an event.
 *
 * - A stream error closes the EventSource and falls back to polling for good.
 * - A hidden tab closes its stream and reopens it once visible: a stream holds one of the
 *   six HTTP/1.1 connections a browser allows per host for as long as it is open.
 * - A 404 while polling means the project was deleted: polling stops and `onGone` runs.
 */
export function useEvents(projectId: string, options: UseEventsOptions = {}) {
  const { pollMs = DEFAULT_POLL_MS, onEvents, onGone } = options;
  const [events, setEvents] = useState<ProjectEvent[]>([]);
  const [mode, setMode] = useState<StreamMode>("connecting");
  const callbacks = useRef({ onEvents, onGone });
  useEffect(() => {
    callbacks.current = { onEvents, onGone };
  });

  useEffect(() => {
    let cancelled = false;
    let cursor = 0;
    let source: EventSource | null = null;
    let polling = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setEvents([]);

    const append = (batch: ProjectEvent[]) => {
      if (cancelled || batch.length === 0) return;
      setEvents((previous) => [...previous, ...batch].slice(-MAX_EVENTS));
      callbacks.current.onEvents?.(batch);
    };

    const poll = async () => {
      try {
        const page = await getEvents(projectId, cursor);
        if (cancelled) return;
        cursor = page.next;
        append(page.events);
      } catch (exc) {
        if (cancelled) return;
        if (exc instanceof ApiError && exc.status === 404) {
          setMode("gone");
          callbacks.current.onGone?.();
          return;
        }
        // A network error or a 5xx: the server may be restarting, keep polling at the same cursor.
      }
      if (!cancelled) timer = setTimeout(poll, pollMs);
    };

    const startPolling = () => {
      polling = true;
      setMode("polling");
      void poll();
    };

    const connect = () => {
      setMode("connecting");
      const stream = new EventSource(streamUrl(projectId, cursor));
      source = stream;
      stream.onopen = () => {
        if (!cancelled) setMode("live");
      };
      stream.onmessage = (message: MessageEvent<string>) => {
        const index = Number.parseInt(message.lastEventId, 10);
        if (Number.isInteger(index)) {
          if (index < cursor) return; // already received (reconnection replay)
          cursor = index + 1;
        } else {
          cursor += 1;
        }
        let event: ProjectEvent;
        try {
          event = JSON.parse(message.data) as ProjectEvent;
        } catch {
          return;
        }
        append([event]);
      };
      stream.onerror = () => {
        stream.close();
        if (source === stream) source = null;
        if (!cancelled) startPolling();
      };
    };

    const onVisibilityChange = () => {
      if (cancelled || polling) return;
      if (isHidden()) {
        source?.close();
        source = null;
        setMode("paused");
      } else if (!source) {
        connect();
      }
    };

    if (typeof EventSource === "undefined") {
      startPolling();
    } else {
      document.addEventListener("visibilitychange", onVisibilityChange);
      if (isHidden()) setMode("paused");
      else connect();
    }

    return () => {
      cancelled = true;
      source?.close();
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [projectId, pollMs]);

  return { events, mode };
}
