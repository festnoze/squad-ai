import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { mockFetch } from "../test/fetchMock";
import { makeSummary } from "../test/fixtures";
import { CreateProjectForm } from "./CreateProjectForm";

const type = (label: string | RegExp, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });

const submit = () => fireEvent.click(screen.getByRole("button", { name: "Créer et lancer" }));

describe("CreateProjectForm", () => {
  it("posts a brief with the chosen profile and hands back the summary", async () => {
    const summary = makeSummary();
    const mock = mockFetch({ "POST /api/v2/projects": { status: 201, body: summary } });
    const onCreated = vi.fn();
    render(<CreateProjectForm onCreated={onCreated} />);

    type("Nom", "  Todo CLI ");
    fireEvent.change(screen.getByLabelText("Profil"), { target: { value: "cli" } });
    type("Brief", "# Todo CLI\nadd, list, done");
    submit();

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(summary));
    expect(mock.calls).toHaveLength(1);
    expect(mock.calls[0].body).toEqual({ name: "Todo CLI", profile: "cli", brief: "# Todo CLI\nadd, list, done" });
  });

  it("posts a goal and leaves the profile to the PO", async () => {
    const mock = mockFetch({ "POST /api/v2/projects": { status: 201, body: makeSummary() } });
    render(<CreateProjectForm onCreated={vi.fn()} />);

    type("Nom", "Notes");
    fireEvent.click(screen.getByLabelText(/Objectif \(le PM/));
    type("Objectif", "une API de notes");
    submit();

    await waitFor(() => expect(mock.calls).toHaveLength(1));
    expect(mock.calls[0].body).toEqual({ name: "Notes", goal: "une API de notes" });
  });

  it("sends the advanced options when they are filled", async () => {
    const mock = mockFetch({ "POST /api/v2/projects": { status: 201, body: makeSummary() } });
    render(<CreateProjectForm onCreated={vi.fn()} />);

    type("Nom", "Compteur");
    fireEvent.change(screen.getByLabelText("Profil"), { target: { value: "fullstack" } });
    type("Brief", "un compteur");
    type("Paquet Python", "counter_app");
    type("Modèle", "sonnet");
    submit();

    await waitFor(() => expect(mock.calls).toHaveLength(1));
    expect(mock.calls[0].body).toEqual({
      name: "Compteur",
      profile: "fullstack",
      brief: "un compteur",
      package: "counter_app",
      model: "sonnet",
    });
  });

  it("refuses to submit without a name or a text", () => {
    const mock = mockFetch({});
    render(<CreateProjectForm onCreated={vi.fn()} />);

    submit();
    expect(screen.getByRole("alert").textContent).toBe("Le nom est obligatoire.");
    type("Nom", "Todo");
    submit();
    expect(screen.getByRole("alert").textContent).toBe("Le brief est obligatoire.");
    expect(mock.calls).toHaveLength(0);
  });

  it("shows the server refusal", async () => {
    mockFetch({ "POST /api/v2/projects": { status: 422, body: { detail: "nom de paquet invalide" } } });
    const onCreated = vi.fn();
    render(<CreateProjectForm onCreated={onCreated} />);

    type("Nom", "Todo");
    type("Brief", "x");
    submit();

    expect((await screen.findByRole("alert")).textContent).toBe("nom de paquet invalide");
    expect(onCreated).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Créer et lancer" }).hasAttribute("disabled")).toBe(false);
  });
});
