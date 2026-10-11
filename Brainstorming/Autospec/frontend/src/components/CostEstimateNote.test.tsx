import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { setLang } from "../i18n/i18n";
import { CostEstimateNote } from "./CostEstimateNote";

afterEach(() => {
  cleanup();
  setLang("en");
});

describe("CostEstimateNote", () => {
  it("keeps an accessible general caveat for older records without completeness metadata", () => {
    const { container } = render(<CostEstimateNote withBudget />);
    expect(screen.getByText("About cost estimates")).toBeVisible();
    expect(container.querySelector("details")).not.toHaveAttribute("open");
    expect(screen.getByText(/not invoices/)).toHaveTextContent("$0 does not guarantee no charge");
    expect(screen.getByText(/execution guardrail/)).toHaveTextContent("not a billing cap");
    expect(screen.queryByText(/Incomplete estimate/)).not.toBeInTheDocument();
    expect(container).not.toHaveTextContent("Team");
    expect(container).not.toHaveTextContent("subscription");
  });

  it("opens a specific incomplete-usage warning when calls are unreported", () => {
    const { container } = render(<CostEstimateNote unreportedCalls={2} />);
    expect(screen.getByText("⚠ Incomplete estimate: 2 call(s) without usage data")).toBeVisible();
    expect(container.querySelector("details")).toHaveAttribute("open");
    expect(screen.getByText(/not invoices/)).toBeVisible();
    expect(screen.queryByText(/execution guardrail/)).not.toBeInTheDocument();
  });

  it("explains estimation, missing usage and the guardrail in French too", () => {
    setLang("fr");
    render(<CostEstimateNote withBudget unreportedCalls={1} />);
    expect(screen.getByText("⚠ Estimation incomplète : 1 appel(s) sans données d'usage")).toBeVisible();
    expect(screen.getByText(/pas des factures/)).toHaveTextContent("$0 ne garantit pas la gratuité");
    expect(screen.getByText(/garde-fou d'exécution/)).toHaveTextContent("pas un plafond de facturation");
  });
});
