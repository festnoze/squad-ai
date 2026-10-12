import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ProjectSetup } from "./ProjectSetup";

describe("ProjectSetup (Q6 — labels a11y)", () => {
  it("tous les champs ont un nom accessible", () => {
    render(<ProjectSetup onCreate={vi.fn()} busy={false} />);
    expect(screen.getByLabelText("Project name")).toBeInTheDocument();
    expect(screen.getByLabelText("Feature or project description")).toBeInTheDocument();
    expect(screen.getByLabelText("Spec to import")).toBeInTheDocument();
    expect(
      screen.getByLabelText(/Path to an existing repo to extend/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Estimated budget in dollars/)).toBeInTheDocument();
  });

  it("soumission désactivée sans objectif, active dès qu'il est rempli", () => {
    const onCreate = vi.fn();
    render(<ProjectSetup onCreate={onCreate} busy={false} />);
    const submit = screen.getByRole("button", { name: /Start the specification/ });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Feature or project description"), {
      target: { value: "Une calculatrice" },
    });
    expect(submit).toBeEnabled();
    fireEvent.click(submit);
    expect(onCreate).toHaveBeenCalledWith(
      "Une calculatrice",
      "",
      false,
      0,
      undefined,
      undefined,
    );
  });

  it("describes the budget as an estimated guardrail and preserves its numeric value", () => {
    const onCreate = vi.fn();
    render(<ProjectSetup onCreate={onCreate} busy={false} />);
    const input = screen.getByLabelText(/Estimated budget in dollars/);
    expect(input).toHaveAccessibleDescription(/execution guardrail.*not a billing cap/);
    expect(screen.getByText(/Calls already running can exceed it/)).toBeVisible();
    fireEvent.change(input, { target: { value: "2.5" } });
    fireEvent.change(screen.getByLabelText("Feature or project description"), { target: { value: "API" } });
    fireEvent.click(screen.getByRole("button", { name: /Start the specification/ }));
    expect(onCreate).toHaveBeenCalledWith("API", "", false, 2.5, undefined, undefined);
  });
});
