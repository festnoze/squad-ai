import { render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FusionMetrics, Metrics } from "../types";

// The dashboard loads everything through GET /api/metrics; only that call and
// the error formatter are needed here.
vi.mock("../api", () => ({
  errorMessage: (e: unknown) => (e instanceof Error ? e.message : String(e)),
  getMetrics: vi.fn(),
}));

import { getMetrics } from "../api";
import { Dashboard } from "./Dashboard";

const getMetricsMock = vi.mocked(getMetrics);

function makeFusion(overrides: Partial<FusionMetrics> = {}): FusionMetrics {
  return {
    suite_runs: 14,
    items_delivered: 4,
    suites_per_item: 3.5,
    canary_verdicts: { pass: 9, revert: 2, inconclusive: 1 },
    canary_reverts: 2,
    canary_batches: 5,
    canary_bisect_reverts: 1,
    merge_requeues: 6,
    requeue_refunds: 3,
    infra_retries: 7,
    p2b_resumes: 0,
    orphan_resets: 0,
    ...overrides,
  };
}

function makeMetrics(overrides: Partial<Metrics> = {}): Metrics {
  return {
    projects: 2,
    total_cost_usd: 1.2345,
    total_tokens: 1000,
    total_agent_calls: 12,
    total_stories: 10,
    stories_done: 8,
    stories_failed: 1,
    success_rate: 80,
    avg_attempts: 1.5,
    cost_per_story: 0.15,
    avg_quality: 82,
    avg_mutation: 70,
    avg_coverage: 91,
    findings: 3,
    regressions: 0,
    ...overrides,
  };
}

describe("Dashboard", () => {
  it("renders the base metric grid once the metrics have loaded", async () => {
    getMetricsMock.mockResolvedValue(makeMetrics());
    render(<Dashboard onClose={vi.fn()} />);
    expect(await screen.findByText("Success rate")).toBeInTheDocument();
    expect(screen.getByText("80%")).toBeInTheDocument();
  });

  it("P3: renders the fusion-loop block when the backend serves `fusion`", async () => {
    getMetricsMock.mockResolvedValue(makeMetrics({ fusion: makeFusion() }));
    render(<Dashboard onClose={vi.fn()} />);
    const block = await screen.findByTestId("dashboard-fusion");
    expect(within(block).getByText("Fusion loop")).toBeInTheDocument();
    // Headline ratio + the raw counters, including the combined cards.
    expect(within(block).getByText("3.5")).toBeInTheDocument();
    expect(within(block).getByText("Suites / delivered item")).toBeInTheDocument();
    expect(within(block).getByText("14")).toBeInTheDocument();
    expect(within(block).getByText("6 / 3")).toBeInTheDocument(); // requeues / refunds
    expect(within(block).getByText("5 / 1")).toBeInTheDocument(); // batches / bisect
    expect(within(block).getByText("7")).toBeInTheDocument(); // infra retries
  });

  it("P3: the canary verdicts are listed key by key, busiest first", async () => {
    getMetricsMock.mockResolvedValue(makeMetrics({ fusion: makeFusion() }));
    render(<Dashboard onClose={vi.fn()} />);
    const list = await screen.findByTestId("fusion-verdicts");
    expect(list.querySelectorAll("li")).toHaveLength(3);
    expect(
      [...list.querySelectorAll(".fusion-verdict-key")].map((e) => e.textContent),
    ).toEqual(["pass", "revert", "inconclusive"]);
  });

  it("P3: an unknown verdict key is rendered too (open histogram)", async () => {
    getMetricsMock.mockResolvedValue(
      makeMetrics({ fusion: makeFusion({ canary_verdicts: { weird_new_verdict: 4 } }) }),
    );
    render(<Dashboard onClose={vi.fn()} />);
    const list = await screen.findByTestId("fusion-verdicts");
    expect(within(list).getByText("weird_new_verdict")).toBeInTheDocument();
  });

  it("P3: no verdict list when the histogram is empty, but the block stays", async () => {
    getMetricsMock.mockResolvedValue(
      makeMetrics({ fusion: makeFusion({ canary_verdicts: {} }) }),
    );
    render(<Dashboard onClose={vi.fn()} />);
    expect(await screen.findByTestId("dashboard-fusion")).toBeInTheDocument();
    expect(screen.queryByTestId("fusion-verdicts")).not.toBeInTheDocument();
  });

  it("P3: no fusion block at all against an older backend (no `fusion` key)", async () => {
    getMetricsMock.mockResolvedValue(makeMetrics());
    render(<Dashboard onClose={vi.fn()} />);
    await screen.findByText("Success rate");
    expect(screen.queryByTestId("dashboard-fusion")).not.toBeInTheDocument();
  });

  it("surfaces a load error instead of the grid", async () => {
    getMetricsMock.mockRejectedValue(new Error("boom"));
    render(<Dashboard onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("boom")).toBeInTheDocument());
    expect(screen.queryByTestId("dashboard-fusion")).not.toBeInTheDocument();
  });
});
