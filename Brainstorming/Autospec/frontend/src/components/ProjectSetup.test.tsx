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
    expect(screen.getByLabelText(/Maximum budget in dollars/)).toBeInTheDocument();
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
});
