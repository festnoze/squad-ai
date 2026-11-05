import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ProjectDetail } from "../api";
import { FakeEventSource } from "../test/FakeEventSource";
import { mockFetch, type Handler } from "../test/fetchMock";
import { makeProject } from "../test/fixtures";
import { ProjectView } from "./ProjectView";

const BASE = "/api/v2/projects/todo-cli";

function setup(project: ProjectDetail, extra: Record<string, Handler> = {}) {
  const mock = mockFetch({
    [`GET ${BASE}`]: { body: project },
    [`GET ${BASE}/files`]: { body: { files: ["pyproject.toml"] } },
    ...extra,
  });
  const onDeleted = vi.fn();
  render(<ProjectView projectId="todo-cli" onDeleted={onDeleted} refreshDelayMs={0} />);
  return { mock, onDeleted };
}

const button = (name: string) => screen.getByRole("button", { name });
/** The events log opens its EventSource in an effect, which can run after findBy* resolves. */
const stream = () => waitFor(() => FakeEventSource.latest());

describe("ProjectView", () => {
  it("renders the phase, cost, stories, error and the automatic resume banner", async () => {
    const resumeAt = Math.floor(Date.now() / 1000) + 25 * 60;
    setup(
      makeProject({
        phase: "needs_attention",
        running: false,
        error: "provider limit: resets at 21:00",
        resume_at: resumeAt,
      }),
    );

    expect(await screen.findByRole("heading", { level: 1, name: "Todo CLI" })).toBeTruthy();
    expect(screen.getByText("À examiner")).toBeTruthy();
    expect(screen.queryByText("en cours")).toBeNull();
    expect(screen.getByText(/0,62/)).toBeTruthy();
    expect(screen.getByText("1/2")).toBeTruthy(); // one story done out of two
    expect(screen.getByText("Ligne de commande (cli)")).toBeTruthy();

    const banner = screen.getByText(/Reprise automatique prévue le/);
    expect(banner.getAttribute("role")).toBe("status");
    expect(banner.textContent).toMatch(/dans (24|25) min/);

    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("provider limit: resets at 21:00");

    expect(screen.getByRole("cell", { name: "Ajouter une tâche" })).toBeTruthy();
    expect(screen.getByRole("cell", { name: "Terminer une tâche" })).toBeTruthy();
  });

  it("has no banner nor error when there is nothing to report", async () => {
    setup(makeProject());
    await screen.findByRole("heading", { level: 1, name: "Todo CLI" });
    expect(screen.queryByText(/Reprise automatique/)).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("en cours")).toBeTruthy();
  });

  it("stops a running project with POST /stop, then reloads it", async () => {
    const { mock } = setup(makeProject({ running: true }), {
      [`POST ${BASE}/stop`]: { status: 202, body: { ok: true } },
    });
    await screen.findByRole("heading", { level: 1 });
    expect(button("Reprendre").hasAttribute("disabled")).toBe(true);
    expect(button("Supprimer").hasAttribute("disabled")).toBe(true);

    mock.routes[`GET ${BASE}`] = { body: makeProject({ running: false, phase: "stopped" }) };
    fireEvent.click(button("Arrêter"));

    await screen.findByText("Arrêté");
    expect(mock.callsTo("POST", `${BASE}/stop`)).toHaveLength(1);
    expect(mock.callsTo("POST", `${BASE}/resume`)).toHaveLength(0);
    expect(button("Arrêter").hasAttribute("disabled")).toBe(true);
  });

  it("resumes a stopped project with POST /resume", async () => {
    const { mock } = setup(makeProject({ running: false, phase: "stopped" }), {
      [`POST ${BASE}/resume`]: { status: 202, body: { ok: true } },
    });
    await screen.findByRole("heading", { level: 1 });
    expect(button("Arrêter").hasAttribute("disabled")).toBe(true);

    fireEvent.click(button("Reprendre"));
    await waitFor(() => expect(mock.callsTo("POST", `${BASE}/resume`)).toHaveLength(1));
    expect(mock.callsTo("POST", `${BASE}/stop`)).toHaveLength(0);
  });

  it("stops a parked project to cancel its automatic resume", async () => {
    const parked = makeProject({ running: false, phase: "needs_attention", resume_at: Date.now() / 1000 + 600 });
    const { mock } = setup(parked, { [`POST ${BASE}/stop`]: { status: 202, body: { ok: true } } });
    await screen.findByRole("heading", { level: 1 });
    expect(button("Reprendre").hasAttribute("disabled")).toBe(false);

    mock.routes[`GET ${BASE}`] = { body: makeProject({ running: false, phase: "stopped", resume_at: null }) };
    fireEvent.click(button("Arrêter"));
    await screen.findByText("Arrêté");
    expect(mock.callsTo("POST", `${BASE}/stop`)).toHaveLength(1);
    expect(screen.queryByText(/Reprise automatique/)).toBeNull();
  });

  it("reloads a running project periodically until its run ends", async () => {
    const mock = mockFetch({
      [`GET ${BASE}`]: { body: makeProject({ running: true }) },
      [`GET ${BASE}/files`]: { body: { files: [] } },
    });
    render(<ProjectView projectId="todo-cli" onDeleted={vi.fn()} refreshMs={20} />);
    await screen.findByText("en cours");

    mock.routes[`GET ${BASE}`] = { body: makeProject({ running: false, phase: "done" }) };
    await screen.findByText("Terminé");
    expect(screen.queryByText("en cours")).toBeNull();
    const calls = mock.callsTo("GET", BASE).length;
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(mock.callsTo("GET", BASE)).toHaveLength(calls); // no polling once finished
  });

  it("cannot resume a finished project", async () => {
    setup(makeProject({ running: false, phase: "done" }));
    await screen.findByRole("heading", { level: 1 });
    expect(button("Reprendre").hasAttribute("disabled")).toBe(true);
  });

  it("shows the reason when the server refuses an action", async () => {
    setup(makeProject({ running: false, phase: "stopped" }), {
      [`POST ${BASE}/resume`]: { status: 409, body: { detail: "already running" } },
    });
    await screen.findByRole("heading", { level: 1 });
    fireEvent.click(button("Reprendre"));
    expect((await screen.findByRole("alert")).textContent).toBe("already running");
  });

  it("deletes only after an explicit confirmation", async () => {
    const { mock, onDeleted } = setup(makeProject({ running: false, phase: "done" }), {
      [`DELETE ${BASE}`]: { status: 204 },
    });
    await screen.findByRole("heading", { level: 1 });

    fireEvent.click(button("Supprimer"));
    expect(screen.getByRole("group", { name: "Confirmation de suppression" }).textContent).toContain(
      "Supprimer définitivement « Todo CLI » ?",
    );
    fireEvent.click(button("Annuler"));
    expect(mock.callsTo("DELETE", BASE)).toHaveLength(0);

    fireEvent.click(button("Supprimer"));
    fireEvent.click(button("Confirmer la suppression"));
    await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1));
    expect(mock.callsTo("DELETE", BASE)).toHaveLength(1);
  });

  it("closes the event stream and stops reloading before it sends DELETE", async () => {
    const parked = makeProject({ running: false, phase: "needs_attention", resume_at: Date.now() / 1000 + 600 });
    const seen: { stream?: number; reloads?: number } = {};
    const mock = mockFetch({
      [`GET ${BASE}`]: { body: parked },
      [`GET ${BASE}/files`]: { body: { files: [] } },
      [`DELETE ${BASE}`]: async () => {
        seen.stream = FakeEventSource.latest().readyState;
        seen.reloads = mock.callsTo("GET", BASE).length;
        await new Promise((resolve) => setTimeout(resolve, 100)); // a slow delete
        return { status: 204 };
      },
    });
    const onDeleted = vi.fn();
    render(<ProjectView projectId="todo-cli" onDeleted={onDeleted} refreshMs={10} />);
    await screen.findByRole("heading", { level: 1 });
    const source = await stream();
    act(() => source.open());

    fireEvent.click(button("Supprimer"));
    fireEvent.click(button("Confirmer la suppression"));
    await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1));
    expect(seen.stream).toBe(FakeEventSource.CLOSED);
    expect(mock.callsTo("GET", BASE)).toHaveLength(seen.reloads!); // no reload while deleting
  });

  it("reopens the event stream when the server refuses the deletion", async () => {
    setup(makeProject({ running: false, phase: "stopped" }), {
      [`DELETE ${BASE}`]: { status: 409, body: { detail: "the workspace cannot be deleted" } },
    });
    await screen.findByRole("heading", { level: 1 });
    const first = await stream();

    fireEvent.click(button("Supprimer"));
    fireEvent.click(button("Confirmer la suppression"));
    expect((await screen.findByRole("alert")).textContent).toBe("the workspace cannot be deleted");
    expect(first.readyState).toBe(FakeEventSource.CLOSED);
    await waitFor(() => expect(FakeEventSource.latest()).not.toBe(first)); // the log remounts after the alert
    expect(screen.getByRole("heading", { name: "Journal" })).toBeTruthy();
  });

  it("says when a reload fails after the first load, until one succeeds", async () => {
    const mock = mockFetch({
      [`GET ${BASE}`]: { body: makeProject({ running: true }) },
      [`GET ${BASE}/files`]: { body: { files: [] } },
    });
    render(<ProjectView projectId="todo-cli" onDeleted={vi.fn()} refreshMs={20} />);
    await screen.findByText("en cours");
    expect(screen.queryByRole("alert")).toBeNull();

    mock.routes[`GET ${BASE}`] = { status: 502 };
    expect((await screen.findByRole("alert")).textContent).toBe("État non actualisé : Erreur HTTP 502");
    expect(screen.getByRole("heading", { level: 1, name: "Todo CLI" })).toBeTruthy(); // the last state stays

    mock.routes[`GET ${BASE}`] = { body: makeProject({ running: true }) };
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  it("says the project is gone when its journal disappears, even when idle", async () => {
    const { mock } = setup(makeProject({ running: false, phase: "done" }), {
      [`GET ${BASE}/events`]: { status: 404, body: { detail: "unknown project todo-cli" } },
    });
    await screen.findByRole("heading", { level: 1, name: "Todo CLI" });

    // Deleted from another tab: the server ends the stream and the project is unknown.
    mock.routes[`GET ${BASE}`] = { status: 404, body: { detail: "unknown project todo-cli" } };
    const source = await stream();
    act(() => source.fail());
    expect(await screen.findByRole("heading", { name: "Projet introuvable" })).toBeTruthy();
  });

  it("says when the project does not exist", async () => {
    mockFetch({ [`GET /api/v2/projects/ghost`]: { status: 404, body: { detail: "unknown project" } } });
    render(<ProjectView projectId="ghost" onDeleted={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "Projet introuvable" })).toBeTruthy();
  });

  it("reloads the state when new events arrive", async () => {
    const { mock } = setup(makeProject());
    await screen.findByRole("heading", { level: 1 });
    expect(mock.callsTo("GET", BASE)).toHaveLength(1);

    mock.routes[`GET ${BASE}`] = { body: makeProject({ phase: "deliver" }) };
    const source = await stream();
    act(() => {
      source.open();
      source.emit({ type: "phase", phase: "deliver" }, 0);
    });

    expect(await screen.findByText("Livraison")).toBeTruthy();
    expect(mock.callsTo("GET", BASE).length).toBeGreaterThanOrEqual(2);
  });

  it("opens the diff of a story", async () => {
    const { mock } = setup(makeProject(), {
      [`GET ${BASE}/stories/US-1/diff`]: { body: { available: true, diff: "+def add():\n-pass" } },
    });
    await screen.findByRole("heading", { level: 1 });

    fireEvent.click(button("Voir le diff de US-1"));
    const diff = await screen.findByLabelText("Diff de US-1");
    expect(diff.textContent).toContain("+def add():");
    expect(mock.callsTo("GET", `${BASE}/stories/US-1/diff`)).toHaveLength(1);

    fireEvent.click(button("Fermer le diff"));
    expect(screen.queryByLabelText("Diff de US-1")).toBeNull();
  });
});
