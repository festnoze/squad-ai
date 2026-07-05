import { describe, expect, it } from "vitest";
import { computeDagView } from "./graph";
import { Epic, Stream, Task, UserStory } from "./types";

const STREAMS: Stream[] = [
  {
    id: "backend",
    kind: "backend",
    language: "python",
    toolchain: "",
    file_root: "",
    primary: true,
  },
];

const EPICS: Epic[] = [
  { id: "E1", title: "Epic un", description: "", iteration: 1 },
  { id: "E2", title: "Epic deux", description: "", iteration: 1 },
];

function story(o: Partial<UserStory> = {}): UserStory {
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
    ...o,
  };
}

function task(o: Partial<Task> = {}): Task {
  return {
    id: "T-1",
    story_id: "US-1",
    stream: "",
    title: "Task",
    description: "",
    acceptance_criteria: [],
    gherkin: "",
    depends_on: [],
    status: "todo",
    attempts: 0,
    last_error: "",
    files_hint: [],
    ...o,
  };
}

const STORIES = [
  story({ id: "US-1", epic_id: "E1" }),
  story({ id: "US-2", epic_id: "E2", depends_on: ["US-1"] }),
];

describe("computeDagView (modèle hiérarchique du graphe)", () => {
  it("tout replié par défaut : un nœud par epic, arête agrégée epic→epic", () => {
    const v = computeDagView(EPICS, STORIES, STREAMS, new Set(), null);
    expect(v.nodes.map((n) => n.id).sort()).toEqual(["E1", "E2"]);
    expect(v.nodes.every((n) => n.type === "item")).toBe(true);
    expect(v.edges).toEqual([
      { id: "E1->E2", source: "E1", target: "E2", crit: expect.any(Boolean) },
    ]);
  });

  it("déplier les epics expose les US et l'arête au niveau US", () => {
    const v = computeDagView(EPICS, STORIES, STREAMS, new Set(["E1", "E2"]), null);
    const byId = new Map(v.nodes.map((n) => [n.id, n]));
    expect(byId.get("E1")?.type).toBe("group");
    expect(byId.get("US-1")?.parentId).toBe("E1");
    expect(v.edges.map((e) => e.id)).toEqual(["US-1->US-2"]);
  });

  it("une US décomposée reste un conteneur repliable de ses tâches", () => {
    const stories = [
      story({
        id: "US-1",
        epic_id: "E1",
        tasks: [task({ id: "T-1" }), task({ id: "T-2", depends_on: ["T-1"] })],
      }),
    ];
    const collapsed = computeDagView(
      [EPICS[0]],
      stories,
      STREAMS,
      new Set(["E1"]),
      null,
    );
    expect(collapsed.nodes.find((n) => n.id === "US-1")?.container).toBe(true);
    expect(collapsed.edges).toEqual([]); // T-1→T-2 interne à US-1 repliée
    const open = computeDagView(
      [EPICS[0]],
      stories,
      STREAMS,
      new Set(["E1", "US-1"]),
      null,
    );
    expect(open.nodes.find((n) => n.id === "T-1")?.parentId).toBe("US-1");
    expect(open.edges.map((e) => e.id)).toEqual(["T-1->T-2"]);
  });

  it("focus sur une US : la dépendance externe apparaît en fantôme + breadcrumb", () => {
    const v = computeDagView(EPICS, STORIES, STREAMS, new Set(), "US-2");
    const byId = new Map(v.nodes.map((n) => [n.id, n]));
    expect(byId.get("US-2")).toBeTruthy();
    expect(byId.get("E1")).toBeUndefined(); // l'autre epic n'est pas rendue
    expect(byId.get("US-1")?.ghost).toBe(true);
    expect(v.edges.map((e) => e.id)).toEqual(["US-1->US-2"]);
    expect(v.focusPath.map((p) => p.id)).toEqual(["E2", "US-2"]);
  });

  it("un focus inconnu retombe sur la vue projet", () => {
    const v = computeDagView(EPICS, STORIES, STREAMS, new Set(), "nope");
    expect(v.focusPath).toEqual([]);
    expect(v.nodes.map((n) => n.id).sort()).toEqual(["E1", "E2"]);
  });
});
