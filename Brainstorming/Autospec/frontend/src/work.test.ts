import { describe, expect, it } from "vitest";
import {
  blockedBy,
  buildWorkGraph,
  canResumeBuild,
  deriveItemView,
  DORMANT_PHASES,
  effectiveStatus,
  elapsedLabel,
  hasBuildableStory,
  hasMultiStream,
  isStageActive,
  isStageDone,
  mergeState,
  STAGE_ORDER,
  stageIndex,
} from "./work";
import { PipelinePhase, ProjectState, Stream, Task, TickItem, UserStory } from "./types";

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
  it("préférer le statut effectif sérialisé par le backend", () => {
    expect(
      effectiveStatus(
        story({
          status: "done",
          effective_status_value: "todo",
          tasks: [task({ id: "T1", status: "done" }), task({ id: "T2", status: "todo" })],
        }),
      ),
    ).toBe("todo");
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

describe("work — stage tracker helpers", () => {
  it("STAGE_ORDER : ordre canonique, done en terminal", () => {
    expect(STAGE_ORDER[0]).toBe("queued");
    expect(STAGE_ORDER[STAGE_ORDER.length - 1]).toBe("done");
    expect(STAGE_ORDER).toContain("implementing");
  });

  it("stageIndex : failed → slot terminal, inconnu → 0", () => {
    expect(stageIndex("queued")).toBe(0);
    expect(stageIndex("failed")).toBe(STAGE_ORDER.length - 1);
    expect(stageIndex("implementing")).toBe(STAGE_ORDER.indexOf("implementing"));
    expect(stageIndex("")).toBe(0);
    expect(stageIndex("garbage")).toBe(0);
  });

  it("isStageDone / isStageActive", () => {
    // current = implementing
    expect(isStageDone("analyzing", "implementing")).toBe(true);
    expect(isStageDone("implementing", "implementing")).toBe(false);
    expect(isStageDone("verifying", "implementing")).toBe(false);
    expect(isStageActive("implementing", "implementing")).toBe(true);
    expect(isStageActive("analyzing", "implementing")).toBe(false);
    // done : tout done, rien actif
    expect(isStageDone("verifying", "done")).toBe(true);
    expect(isStageActive("done", "done")).toBe(false);
    // failed : aucune cellule done, aucune active
    expect(isStageDone("analyzing", "failed")).toBe(false);
    expect(isStageActive("implementing", "failed")).toBe(false);
  });

  it("elapsedLabel : formats + cas limites", () => {
    const now = 1_000_000_000_000; // ms
    const nowS = now / 1000;
    expect(elapsedLabel(0, now)).toBe("");
    expect(elapsedLabel(undefined, now)).toBe("");
    expect(elapsedLabel(nowS - 5, now)).toBe("5s");
    expect(elapsedLabel(nowS - 90, now)).toBe("1m 30s");
    expect(elapsedLabel(nowS - 3660, now)).toBe("1h 1m");
    // horloge décalée (départ dans le futur) → ""
    expect(elapsedLabel(nowS + 10, now)).toBe("");
  });
});

function project(overrides: Partial<ProjectState> = {}): ProjectState {
  return {
    id: "p1",
    name: "Projet",
    goal: "",
    auto_spec: false,
    spec_mode: "interview",
    phase: "done" as PipelinePhase,
    brief: "",
    backlog: [],
    epics: [],
    stories: [],
    chat: [],
    feedback: [],
    iteration: 0,
    running: false,
    paused: false,
    error: "",
    created_at: 0,
    architecture: "",
    plan_quality: 0,
    budget_usd: 0,
    archived: false,
    ...overrides,
  };
}

describe("work — canResumeBuild (gating partagé RunPanel/ProjectBar)", () => {
  it("DORMANT_PHASES inclut 'done' (régression snake) en plus de stopped/error", () => {
    expect(DORMANT_PHASES).toContain("done");
    expect(DORMANT_PHASES).toContain("stopped");
    expect(DORMANT_PHASES).toContain("error");
  });

  it("phase 'done' avec story 'todo' restante → true (le cas snake : 5/9 faites)", () => {
    expect(
      canResumeBuild(
        project({
          phase: "done",
          stories: [story({ id: "S1", status: "done" }), story({ id: "S2", status: "todo" })],
        }),
      ),
    ).toBe(true);
  });

  it.each<PipelinePhase>(["stopped", "error"])(
    "phase dormante '%s' avec story todo → true",
    (phase) => {
      expect(
        canResumeBuild(project({ phase, stories: [story({ status: "todo" })] })),
      ).toBe(true);
    },
  );

  it("phase active (build) même avec story todo → false (pipeline en cours)", () => {
    expect(
      canResumeBuild(project({ phase: "build", stories: [story({ status: "todo" })] })),
    ).toBe(false);
  });

  it("phase 'done' mais toutes les stories done → false", () => {
    expect(
      canResumeBuild(project({ phase: "done", stories: [story({ status: "done" })] })),
    ).toBe(false);
  });

  it("statut EFFECTIF : US multi-stream à moitié faite (tasks [done, todo], status brut 'done') → true", () => {
    const half = story({
      status: "done",
      tasks: [task({ id: "T1", status: "done" }), task({ id: "T2", status: "todo" })],
    });
    expect(canResumeBuild(project({ phase: "done", stories: [half] }))).toBe(true);
    expect(hasBuildableStory([half])).toBe(true);
  });
});

describe("work — deriveItemView", () => {
  it("sans tick : retombe sur les champs persistés", () => {
    const s = story({
      status: "in_progress",
      current_stage: "implementing",
      stage_started_at: 123,
      current_persona: "dev",
      recovery: { attempt: 1, max_attempts: 3, kind: "refining" },
    });
    const v = deriveItemView(s);
    expect(v.kind).toBe("story");
    expect(v.fromTick).toBe(false);
    expect(v.stage).toBe("implementing");
    expect(v.persona).toBe("dev");
    expect(v.recovery.kind).toBe("refining");
    expect(v.stageStartedAt).toBe(123);
  });

  it("avec tick : le tick gagne pour stage/persona/status, guidance reste de l'état", () => {
    const s = story({
      status: "todo",
      current_stage: "queued",
      guidance: [{ id: "g1", text: "fix", ts: 1, status: "queued" }],
    });
    const tick: TickItem = {
      id: "US-1",
      kind: "story",
      status: "in_progress",
      current_stage: "verifying",
      stage_started_at: 999,
      current_persona: "qa",
      recovery: { attempt: 2, max_attempts: 3, kind: "retry" },
    };
    const v = deriveItemView(s, tick);
    expect(v.fromTick).toBe(true);
    expect(v.status).toBe("in_progress");
    expect(v.stage).toBe("verifying");
    expect(v.persona).toBe("qa");
    expect(v.stageStartedAt).toBe(999);
    expect(v.guidance).toHaveLength(1); // toujours de l'état
  });

  it("task → kind task", () => {
    const v = deriveItemView(task({ id: "T1", current_stage: "contracts" }));
    expect(v.kind).toBe("task");
    expect(v.stage).toBe("contracts");
  });
});
