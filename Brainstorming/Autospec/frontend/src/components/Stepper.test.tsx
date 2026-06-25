import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Stepper, STALE_MS } from "./Stepper";
import { ItemView } from "../work";
import { RecoveryState } from "../types";

const NO_RECOVERY: RecoveryState = { attempt: 0, max_attempts: 0, kind: "" };

function view(overrides: Partial<ItemView> = {}): ItemView {
  return {
    id: "US-1",
    kind: "story",
    status: "in_progress",
    stage: "implementing",
    stageStartedAt: 0,
    persona: "dev",
    recovery: NO_RECOVERY,
    guidance: [],
    fromTick: true,
    ...overrides,
  };
}

describe("Stepper", () => {
  it("marque l'étape courante active et les précédentes done", () => {
    render(<Stepper view={view({ stage: "implementing" })} now={Date.now()} />);
    expect(screen.getByTestId("stage-US-1-implementing")).toHaveAttribute(
      "data-state",
      "active",
    );
    expect(screen.getByTestId("stage-US-1-analyzing")).toHaveAttribute(
      "data-state",
      "done",
    );
    expect(screen.getByTestId("stage-US-1-verifying")).toHaveAttribute(
      "data-state",
      "pending",
    );
  });

  it("statut done : toutes les cellules done", () => {
    render(<Stepper view={view({ status: "done", stage: "done" })} now={Date.now()} />);
    expect(screen.getByTestId("stage-US-1-verifying")).toHaveAttribute(
      "data-state",
      "done",
    );
    expect(screen.getByTestId("stage-US-1-done")).toHaveAttribute(
      "data-state",
      "done",
    );
  });

  it("statut failed : la cellule terminale est failed", () => {
    render(<Stepper view={view({ status: "failed", stage: "failed" })} now={Date.now()} />);
    expect(screen.getByTestId("stage-US-1-done")).toHaveAttribute(
      "data-state",
      "failed",
    );
  });

  it("affiche l'elapsed sur l'étape active", () => {
    const now = 1_000_000_000_000;
    render(
      <Stepper
        view={view({ stage: "implementing", stageStartedAt: now / 1000 - 42 })}
        now={now}
      />,
    );
    const cell = screen.getByTestId("stage-US-1-implementing");
    expect(cell).toHaveTextContent("42s");
  });

  it("sous-ligne recovery quand kind défini", () => {
    render(
      <Stepper
        view={view({ recovery: { attempt: 2, max_attempts: 3, kind: "refining" } })}
        now={Date.now()}
      />,
    );
    expect(screen.getByTestId("recovery-US-1")).toHaveTextContent("2/3");
    expect(screen.getByTestId("recovery-US-1")).toHaveTextContent(/refining/i);
  });

  it("grise (stale) quand le tick a plus de 25s", () => {
    const now = 2_000_000;
    render(<Stepper view={view()} now={now} tickTs={now - STALE_MS - 1000} />);
    expect(screen.getByTestId("stepper-US-1")).toHaveAttribute("data-stale", "true");
  });

  it("pas stale quand le tick est récent", () => {
    const now = 2_000_000;
    render(<Stepper view={view()} now={now} tickTs={now - 1000} />);
    expect(screen.getByTestId("stepper-US-1")).toHaveAttribute("data-stale", "false");
  });
});
