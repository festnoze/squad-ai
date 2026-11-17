import { describe, expect, it } from "vitest";
import {
  ApiError,
  createProject,
  deleteProject,
  getEvents,
  getProject,
  getStoryDiff,
  listProjects,
  readFile,
  resumeProject,
  stopProject,
  streamUrl,
} from "./api";
import { mockFetch } from "./test/fetchMock";
import { makeSummary } from "./test/fixtures";

describe("api client", () => {
  it("lists the projects", async () => {
    mockFetch({ "GET /api/v2/projects": { body: [makeSummary()] } });
    const projects = await listProjects();
    expect(projects.map((p) => p.id)).toEqual(["todo-cli"]);
  });

  it("posts the creation body as JSON", async () => {
    const mock = mockFetch({ "POST /api/v2/projects": { status: 201, body: makeSummary() } });
    const created = await createProject({ name: "Todo CLI", profile: "cli", goal: "une todo" });
    expect(created.id).toBe("todo-cli");
    const [call] = mock.calls;
    expect(call.body).toEqual({ name: "Todo CLI", profile: "cli", goal: "une todo" });
    expect(call.headers["Content-Type"]).toBe("application/json");
  });

  it("calls the resume and stop endpoints with POST", async () => {
    const mock = mockFetch({
      "POST /api/v2/projects/p1/resume": { status: 202, body: { ok: true } },
      "POST /api/v2/projects/p1/stop": { status: 202, body: { ok: true } },
    });
    expect(await resumeProject("p1")).toEqual({ ok: true });
    expect(await stopProject("p1")).toEqual({ ok: true });
    expect(mock.calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      "POST /api/v2/projects/p1/resume",
      "POST /api/v2/projects/p1/stop",
    ]);
  });

  it("resolves a 204 delete without a body", async () => {
    mockFetch({ "DELETE /api/v2/projects/p1": { status: 204 } });
    await expect(deleteProject("p1")).resolves.toBeUndefined();
  });

  it("raises an ApiError carrying the FastAPI detail", async () => {
    mockFetch({ "POST /api/v2/projects/p1/resume": { status: 409, body: { detail: "le projet tourne déjà" } } });
    const error = await resumeProject("p1").catch((exc: unknown) => exc);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(409);
    expect((error as ApiError).message).toBe("le projet tourne déjà");
  });

  it("joins validation messages and falls back to the status", async () => {
    mockFetch({
      "POST /api/v2/projects": { status: 422, body: { detail: [{ loc: ["body"], msg: "brief or goal required" }] } },
      "GET /api/v2/projects/p1": { status: 500 },
    });
    await expect(createProject({ name: "x" })).rejects.toThrow("brief or goal required");
    await expect(getProject("p1")).rejects.toThrow("Erreur HTTP 500");
  });

  it("encodes ids, story ids and file paths", async () => {
    const mock = mockFetch({
      "GET /api/v2/projects/a%20b": { body: {} },
      "GET /api/v2/projects/p1/files/raw": { body: { path: "pkg/app.py", content: "", truncated: false } },
      "GET /api/v2/projects/p1/stories/US-1/diff": { body: { available: false, diff: "" } },
      "GET /api/v2/projects/p1/events": { body: { events: [], next: 7 } },
    });
    await getProject("a b");
    await readFile("p1", "pkg/app.py");
    await getStoryDiff("p1", "US-1");
    expect(await getEvents("p1", 7)).toEqual({ events: [], next: 7 });
    expect(mock.calls[1].search.get("path")).toBe("pkg/app.py");
    expect(mock.calls[1].url).toContain("path=pkg%2Fapp.py");
    expect(mock.calls[3].search.get("after")).toBe("7");
    expect(streamUrl("p1")).toBe("/api/v2/projects/p1/stream");
    expect(streamUrl("p1", 0)).toBe("/api/v2/projects/p1/stream");
    expect(streamUrl("p1", 7)).toBe("/api/v2/projects/p1/stream?after=7");
  });
});
