import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { setLang } from "../i18n/i18n";
import { AgentExecutionPanel } from "./AgentExecutionPanel";

afterEach(() => { cleanup(); setLang("en"); });

it("distinguishes one provider call from the worker waiting for budget", () => {
  setLang("en");
  render(<AgentExecutionPanel activities={{
    T1: { version: 1, phase: "provider", since: Date.now()/1000, active_provider_calls: 1, cost_incomplete: false },
    T2: { version: 1, phase: "waiting_budget", since: Date.now()/1000, owner: ["T1"], active_provider_calls: 1, cost_incomplete: false },
  }} />);
  expect(screen.getByText("1 active provider calls")).toBeVisible();
  expect(screen.getByText(/T2 — Waiting for estimated budget/)).toBeVisible();
  expect(screen.getByText(/T1 — Provider call in progress/)).toBeVisible();
});

it("keeps incomplete cost visible after calls have disappeared", () => {
  render(<AgentExecutionPanel incomplete />);
  expect(screen.getByRole("status")).toHaveTextContent(/Recorded cost is incomplete/);
});

it("never labels file/test/merge waits as provider execution", () => {
  render(<AgentExecutionPanel activities={Object.fromEntries(
    ["waiting_claim", "dependency", "tests", "waiting_merge", "repair"].map(phase => [phase,
      {version: 1, phase, since: Date.now()/1000, active_provider_calls: 0, cost_incomplete: false}]))} />);
  expect(screen.getByText(/0 active provider calls/)).toBeVisible();
  expect(screen.getByText(/Waiting for file ownership/)).toBeVisible();
  expect(screen.getByText(/Running isolated tests/)).toBeVisible();
  expect(screen.getByText(/Waiting for merge ownership/)).toBeVisible();
  expect(screen.queryByText(/Provider call in progress/)).not.toBeInTheDocument();
});
