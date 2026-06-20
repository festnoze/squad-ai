import { describe, expect, it } from "vitest";
import {
  blockedBy,
  buildWorkGraph,
  effectiveStatus,
  hasMultiStream,
  mergeState,
} from "./work";
import { Stream, Task, UserStory } from "./types";

function task(overrides: Partial<Task> = {}): Task {
  return {
    id: "T1",
    story_id: "US-1",
    stream: "",
    title: "Tâche",
    description: "",
    acceptance_criteria: [],
    gherkin: "",
    depends_on: [],
    status: "todo",
    attempts: 0,
    last_error: "",
    files_hint: [],
    ...overrides,
  };
}

function story(overrides: Partial<UserStory> = {}): UserStory {
  return {
    id: "US-1",
    epic_id: "E1",
    title: "US",
    description: "",
    acceptance_criteria: [],
    gherkin: "",
    test_plan: [],
    depends_on: [],
    priority: 3,
    status: "todo",
    iteration: 1,
    attempts: 0,
    last_error: "",
    quality_score: -1,
    ...overrides,
  };
}

const STREAMS: Stream[] = [
  { id: "backend", kind: "backend", language: "python", toolchain: "", file_root: "", primary: true },
  { id: "frontend", kind: "frontend", language: "react", toolchain: "", file_root: "frontend", primary: false },
];

describe("work — effectiveStatus", () => {
  it("US sans tâches : statut stocké", () => {
    expect(effectiveStatus(story({ status: "failed" }))).toBe("failed");
  });
  it("US décomposée : toutes tâches done → done", () => {
    const s = story({
      tasks: [task({ id: "T1", status: "done" }), task({ id: "T2", status: "done" })],
    });
    expect(effectiveStatus(s)).toBe("done");
  });
  it("US décomposée : une tâche active → in_progress", () => {
    const s = story({
      tasks: [task({ id: "T1", status: "done" }), task({ id: "T2", status: "in_progress" })],
    });
    expect(effectiveStatus(s)).toBe("in_progress");
  });
  it("US décomposée : une tâche failed (et aucune active) → failed", () => {
    const s = story({
      tasks: [task({ id: "T1", status: "failed" }), task({ id: "T2", status: "todo" })],
    });
    expect(effectiveStatus(s)).toBe("failed");
  });
});

describe("work — work graph + blockedBy", () => {
  it("tâche bloquée par sa dépendance non done", () => {
    const s = story({
      tasks: [
        task({ id: "T-back", status: "in_progress" }),
        task({ id: "T-front", stream: "frontend", depends_on: ["T-back"] }),
      ],
    });
    const graph = buildWorkGraph([s], STREAMS);
    expect(blockedBy("T-front", graph)).toEqual(["T-back"]);
    // une fois la dépendance done, plus de blocage
    s.tasks![0].status = "done";
    const g2 = buildWorkGraph([s], STREAMS);
    expect(blockedBy("T-front", g2)).toEqual([]);
  });

  it("dépendance US→US décomposée se résout vers toutes ses tâches", () => {
    const a = story({ id: "US-A", tasks: [task({ id: "A1", status: "todo" })] });
    const b = story({ id: "US-B", depends_on: ["US-A"] });
    const graph = buildWorkGraph([a, b], STREAMS);
    expect(blockedBy("US-B", graph)).toEqual(["A1"]);
  });
});

describe("work — mergeState + hasMultiStream", () => {
  it("done → mergé ; failed+conflit → conflict ; sinon null", () => {
    expect(mergeState("done")).toBe("merged");
    expect(mergeState("failed", "conflit de merge inter-stream non résolu")).toBe("conflict");
    expect(mergeState("failed", "boom")).toBeNull();
    expect(mergeState("todo")).toBeNull();
  });

  it("hasMultiStream : >1 stream OU présence de tâches", () => {
    expect(hasMultiStream(STREAMS, [story()])).toBe(true);
    expect(hasMultiStream([], [story({ tasks: [task()] })])).toBe(true);
    expect(hasMultiStream([], [story()])).toBe(false);
    expect(hasMultiStream(undefined, [story()])).toBe(false);
  });
});
