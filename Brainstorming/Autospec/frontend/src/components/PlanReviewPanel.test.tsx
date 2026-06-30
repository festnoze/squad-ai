import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PlanReviewPanel } from "./PlanReviewPanel";

describe("PlanReviewPanel (Revue du plan)", () => {
  it("ne rend rien tant que la revue n'a pas tourné", () => {
    const { container } = render(
      <PlanReviewPanel planQuality={-1} issues={[]} suggestions={[]} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("affiche le score, les problèmes et les suggestions du critic", () => {
    render(
      <PlanReviewPanel
        planQuality={72}
        issues={["US-3 trop grosse pour une session"]}
        suggestions={["découper US-3 en 2 tâches"]}
      />,
    );
    expect(screen.getByTestId("plan-review-score").textContent).toContain("72/100");
    expect(screen.getByText(/US-3 trop grosse/)).toBeTruthy();
    expect(screen.getByText(/découper US-3/)).toBeTruthy();
  });

  it("score bon sans problème → état propre", () => {
    render(<PlanReviewPanel planQuality={95} issues={[]} suggestions={[]} />);
    const score = screen.getByTestId("plan-review-score");
    expect(score.textContent).toContain("95/100");
    expect(score.className).toContain("plan-review-score-good");
  });
});
