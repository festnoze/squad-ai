import { act, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProjectEvent } from "../api";
import { FakeEventSource } from "../test/FakeEventSource";
import { mockFetch } from "../test/fetchMock";
import { EventsLog, eventSummary, eventTone } from "./EventsLog";

const EVENTS = "/api/v2/projects/p1/events";

const lines = () => within(screen.getByRole("log", { name: "Événements du projet" })).getAllByRole("listitem");

/** Serves the given pages one after the other, then empty pages at the last cursor. */
function pagedEvents(pages: { events: ProjectEvent[]; next: number }[]) {
  let served = 0;
  return () => {
    const page = pages[Math.min(served, pages.length - 1)];
    const body = served < pages.length ? page : { events: [], next: page.next };
    served += 1;
    return { body };
  };
}

/** Pretends the tab is shown or hidden; the real getter comes back in afterEach. */
function setVisibility(state: DocumentVisibilityState, notify = true) {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
  if (notify) document.dispatchEvent(new Event("visibilitychange"));
}

afterEach(() => {
  delete (document as { visibilityState?: unknown }).visibilityState;
});

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

describe("EventsLog", () => {
  it("appends the events pushed by the stream, in order and without duplicates", () => {
    const onEvents = vi.fn();
    render(<EventsLog projectId="p1" onEvents={onEvents} />);
    const source = FakeEventSource.latest();
    expect(source.url).toBe("/api/v2/projects/p1/stream");
    expect(screen.getByRole("status").textContent).toBe("Connexion...");
    expect(screen.getByText("Aucun événement pour l'instant.")).toBeTruthy();

    act(() => {
      source.open();
      source.emit({ ts: "2026-11-02T18:00:00+00:00", type: "phase", phase: "plan" }, 0);
      source.emit({ ts: "2026-11-02T18:00:05+00:00", type: "plan", stories: ["US-1"], profile: "cli" }, 1);
      source.emit({ type: "phase", phase: "plan" }, 0); // a reconnection replay
      source.emit({ type: "suite", purpose: "verify", id: "US-1", ok: false }, 2);
    });

    expect(screen.getByRole("status").textContent).toBe("En direct");
    const items = lines();
    expect(items).toHaveLength(3);
    expect(items[0].textContent).toContain("Phase");
    expect(items[0].textContent).toContain("phase=plan");
    expect(items[0].querySelector("time")?.getAttribute("dateTime")).toBe("2026-11-02T18:00:00+00:00");
    expect(items[1].textContent).toContain('stories=["US-1"]');
    expect(items[2].textContent).toContain("Suite de tests");
    expect(items[2].className).toBe("bad");
    expect(onEvents).toHaveBeenCalledTimes(3);
  });

  it("ignores a message that is not JSON", () => {
    render(<EventsLog projectId="p1" />);
    const source = FakeEventSource.latest();
    act(() => {
      source.onmessage?.(new MessageEvent("message", { data: "not json", lastEventId: "0" }));
      source.emit({ type: "end", phase: "done" }, 1);
    });
    expect(lines()).toHaveLength(1);
  });

  it("falls back to polling after a stream error, from the next index", async () => {
    const mock = mockFetch({
      [`GET ${EVENTS}`]: pagedEvents([
        { events: [{ type: "smoke", ok: true }], next: 3 },
        { events: [{ type: "end", phase: "done" }], next: 4 },
      ]),
    });
    render(<EventsLog projectId="p1" pollMs={10} />);
    const source = FakeEventSource.latest();
    act(() => {
      source.open();
      source.emit({ type: "phase", phase: "build" }, 0);
      source.emit({ type: "phase", phase: "deliver" }, 1);
      source.fail();
    });

    expect(source.readyState).toBe(FakeEventSource.CLOSED);
    expect(screen.getByRole("status").textContent).toBe("Interrogation périodique");
    await waitFor(() => expect(lines()).toHaveLength(4));
    const cursors = mock.callsTo("GET", EVENTS).map((call) => call.search.get("after"));
    expect(cursors.slice(0, 2)).toEqual(["2", "3"]);
    expect(lines()[3].textContent).toContain("Fin");
    expect(lines()[2].className).toBe("good");
  });

  it("polls from the start when the browser has no EventSource", async () => {
    vi.stubGlobal("EventSource", undefined);
    const mock = mockFetch({
      [`GET ${EVENTS}`]: pagedEvents([{ events: [{ type: "phase", phase: "brief" }], next: 1 }]),
    });
    render(<EventsLog projectId="p1" pollMs={10} />);

    expect(screen.getByRole("status").textContent).toBe("Interrogation périodique");
    await waitFor(() => expect(lines()).toHaveLength(1));
    await waitFor(() => expect(mock.callsTo("GET", EVENTS).length).toBeGreaterThanOrEqual(2));
    expect(mock.callsTo("GET", EVENTS)[0].search.get("after")).toBe("0");
    expect(mock.callsTo("GET", EVENTS)[1].search.get("after")).toBe("1");
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it("keeps its cursor while the server cannot answer", async () => {
    vi.stubGlobal("EventSource", undefined);
    let calls = 0;
    const mock = mockFetch({
      [`GET ${EVENTS}`]: () => {
        calls += 1;
        return calls === 1 ? { status: 502 } : { body: { events: calls === 2 ? [{ type: "plan" }] : [], next: 1 } };
      },
    });
    render(<EventsLog projectId="p1" pollMs={10} />);

    await waitFor(() => expect(lines()).toHaveLength(1));
    const cursors = mock.callsTo("GET", EVENTS).map((call) => call.search.get("after"));
    expect(cursors.slice(0, 2)).toEqual(["0", "0"]);
  });

  it("stops polling and reports it when the project is gone (404)", async () => {
    const onGone = vi.fn();
    const mock = mockFetch({ [`GET ${EVENTS}`]: { status: 404, body: { detail: "unknown project p1" } } });
    render(<EventsLog projectId="p1" pollMs={10} onGone={onGone} />);
    act(() => FakeEventSource.latest().fail()); // the server ends the stream of a deleted project

    await waitFor(() => expect(onGone).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("status").textContent).toBe("Projet introuvable");
    await sleep(60);
    expect(mock.callsTo("GET", EVENTS)).toHaveLength(1);
    expect(onGone).toHaveBeenCalledTimes(1);
  });

  it("closes the stream of a hidden tab and resumes it from the cursor once visible", () => {
    render(<EventsLog projectId="p1" />);
    const first = FakeEventSource.latest();
    act(() => {
      first.open();
      first.emit({ type: "phase", phase: "plan" }, 0);
      first.emit({ type: "phase", phase: "build" }, 1);
    });

    act(() => setVisibility("hidden"));
    expect(first.readyState).toBe(FakeEventSource.CLOSED);
    expect(screen.getByRole("status").textContent).toBe("En pause (onglet masqué)");
    expect(FakeEventSource.instances).toHaveLength(1);

    act(() => setVisibility("visible"));
    const second = FakeEventSource.latest();
    expect(second).not.toBe(first);
    expect(second.url).toBe("/api/v2/projects/p1/stream?after=2");
    act(() => {
      second.open();
      second.emit({ type: "phase", phase: "build" }, 1); // a server that ignores ?after
      second.emit({ type: "end", phase: "done" }, 2);
    });
    expect(screen.getByRole("status").textContent).toBe("En direct");
    expect(lines().map((line) => line.textContent)).toEqual([
      expect.stringContaining("phase=plan"),
      expect.stringContaining("phase=build"),
      expect.stringContaining("Fin"),
    ]);
  });

  it("waits until a tab opened in the background is shown before connecting", () => {
    setVisibility("hidden", false);
    render(<EventsLog projectId="p1" />);
    expect(FakeEventSource.instances).toHaveLength(0);
    expect(screen.getByRole("status").textContent).toBe("En pause (onglet masqué)");

    act(() => setVisibility("visible"));
    expect(FakeEventSource.latest().url).toBe("/api/v2/projects/p1/stream");
  });

  it("keeps polling in a hidden tab after a stream error", async () => {
    const mock = mockFetch({ [`GET ${EVENTS}`]: { body: { events: [], next: 0 } } });
    render(<EventsLog projectId="p1" pollMs={10} />);
    act(() => FakeEventSource.latest().fail());
    act(() => setVisibility("hidden"));
    act(() => setVisibility("visible"));

    expect(screen.getByRole("status").textContent).toBe("Interrogation périodique");
    expect(FakeEventSource.instances).toHaveLength(1);
    await waitFor(() => expect(mock.callsTo("GET", EVENTS).length).toBeGreaterThanOrEqual(2));
  });

  it("closes the stream when it unmounts", () => {
    const { unmount } = render(<EventsLog projectId="p1" />);
    const source = FakeEventSource.latest();
    unmount();
    expect(source.readyState).toBe(FakeEventSource.CLOSED);
  });
});

describe("event formatting", () => {
  it("summarises every field but the timestamp and the type", () => {
    const summary = eventSummary({ ts: "x", type: "agent_end", role: "dev", cost_usd: 0.12, turns: 9 });
    expect(summary).toBe("role=dev  cost_usd=0.12  turns=9");
    expect(eventSummary({ type: "end", phase: "done", id: "", resume_at: null, ok: false })).toBe("phase=done  ok=false");
    expect(eventSummary({ type: "qa_rejected", reason: "y".repeat(400) })).toHaveLength("reason=".length + 303);
  });

  it("colours failures and successes", () => {
    expect(eventTone({ type: "verify_failed" })).toBe("bad");
    expect(eventTone({ type: "smoke", ok: false })).toBe("bad");
    expect(eventTone({ type: "suite", ok: true })).toBe("good");
    expect(eventTone({ type: "phase", phase: "build" })).toBe("");
  });
});
