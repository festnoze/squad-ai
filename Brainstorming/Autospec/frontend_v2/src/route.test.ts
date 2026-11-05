import { describe, expect, it } from "vitest";
import { parseHash, routeHash } from "./route";

describe("parseHash", () => {
  it("reads the project list and project views", () => {
    expect(parseHash("")).toEqual({ name: "list" });
    expect(parseHash("#/")).toEqual({ name: "list" });
    expect(parseHash("#/projects/todo-cli-1a2b3c4d")).toEqual({ name: "project", id: "todo-cli-1a2b3c4d" });
    expect(parseHash("#/projects/notes_v1.2/")).toEqual({ name: "project", id: "notes_v1.2" });
  });

  it("falls back to the list for ids the server can never have", () => {
    // "." and ".." would collapse into other API routes (/api/v2/projects/ or /api/v2/).
    for (const hash of ["#/projects/.", "#/projects/..", "#/projects/%2E%2E", "#/projects/a%2Fb", "#/projects/-x", "#/projects/%E0%A4%A"]) {
      expect(parseHash(hash)).toEqual({ name: "list" });
    }
    expect(parseHash(`#/projects/${"a".repeat(129)}`)).toEqual({ name: "list" });
  });

  it("round-trips with routeHash", () => {
    const route = { name: "project", id: "todo-cli-1a2b3c4d" } as const;
    expect(parseHash(routeHash(route))).toEqual(route);
    expect(routeHash({ name: "list" })).toBe("#/");
  });
});
