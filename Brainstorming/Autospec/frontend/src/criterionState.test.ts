import { describe, expect, it } from "vitest";
import {
  AcceptanceCriterion,
  criterionState,
  PlannedTest,
  StoryStatus,
  TestState,
  UserStory,
} from "./types";

const CRITERION: AcceptanceCriterion = { id: "c1", text: "Le critère 1" };

function makeTest(
  id: string,
  status: TestState,
  criteria: string[] = ["c1"],
): PlannedTest {
  return {
    id,
    layer: "unit",
    description: `test ${id}`,
    mocks: [],
    file_hint: "",
    criteria,
    status,
  };
}

function makeStory(
  status: StoryStatus,
  testPlan: PlannedTest[],
): UserStory {
  return {
    id: "S1",
    epic_id: "E1",
    title: "Story de test",
    description: "",
    acceptance_criteria: [CRITERION],
    gherkin: "",
    test_plan: testPlan,
    depends_on: [],
    priority: 3,
    status,
    iteration: 0,
    attempts: 0,
    last_error: "",
  };
}

describe("criterionState", () => {
  it("retourne 'green' quand la story est 'done', peu importe les tests", () => {
    const story = makeStory("done", [makeTest("t1", "red")]);
    expect(criterionState(story, CRITERION)).toBe("green");
  });

  it("retourne 'green' quand tous les tests du critère sont verts", () => {
    const story = makeStory("in_progress", [
      makeTest("t1", "green"),
      makeTest("t2", "green"),
    ]);
    expect(criterionState(story, CRITERION)).toBe("green");
  });

  it("retourne 'red' dès qu'un test du critère est rouge", () => {
    const story = makeStory("in_progress", [
      makeTest("t1", "green"),
      makeTest("t2", "red"),
    ]);
    expect(criterionState(story, CRITERION)).toBe("red");
  });

  it("retourne 'nonexistent' quand aucun test n'est rattaché au critère", () => {
    const story = makeStory("in_progress", []);
    expect(criterionState(story, CRITERION)).toBe("nonexistent");
  });

  it("retourne 'nonexistent' pour un mélange vert + critère sans test (story non done)", () => {
    // t1 cible un autre critère → le critère c1 n'a aucun test rattaché.
    const story = makeStory("in_progress", [makeTest("t1", "green", ["other"])]);
    expect(criterionState(story, CRITERION)).toBe("nonexistent");
  });
});
