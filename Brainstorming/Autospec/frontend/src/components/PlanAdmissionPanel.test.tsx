import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { setLang } from "../i18n/i18n";
import { PlanAdmissionPanel } from "./PlanAdmissionPanel";

const projection = {
  version: 1, admission_version: 1, status: "fail", contract_hash: "a".repeat(64),
  candidate_sha256: "b".repeat(64), candidate_bytes: 123, candidate_available: true,
  capture_complete: true, receipt_sha256: "c".repeat(64), lot_count: 8,
  diagnostics: [{ code: "lot_limit", severity: "error", diagnostic_sha256: "d".repeat(64) }], diagnostics_omitted: 0,
};
afterEach(() => { cleanup(); setLang("en"); });
describe("safe plan admission telemetry", () => {
  it("shows rejected constraints and exact identity without a judge score", () => {
    render(<PlanAdmissionPanel diagnostic={projection} />);
    expect(screen.getByRole("status").textContent).toBe("Plan rejected by constraints");
    expect(screen.getByRole("region", { name: "Plan admission" })).toBeTruthy();
    expect(screen.getByText("b".repeat(64))).toBeTruthy();
    expect(screen.getByText(/maximum number of lots/)).toBeTruthy();
  });
  it("renders French and preserves omitted diagnostic count", () => {
    setLang("fr"); render(<PlanAdmissionPanel diagnostic={{ ...projection, diagnostics_omitted: 12 }} />);
    expect(screen.getByRole("status").textContent).toBe("Plan refusé par les contraintes");
    expect(screen.getByText(/Diagnostics supplémentaires non affichés: 12/)).toBeTruthy();
    expect(screen.getByRole("region", { name: "Admission du plan" })).toBeTruthy();
  });
  it("never renders unknown maker fields or malicious diagnostic codes", () => {
    render(<PlanAdmissionPanel diagnostic={{ ...projection, response: "SECRET_PASSWORD full brief",
      errors: ["SECRET_PASSWORD"], diagnostics: [{ ...projection.diagnostics[0], code: "<img onerror=secret>" }] }} />);
    expect(document.body.textContent).not.toContain("SECRET_PASSWORD");
    expect(document.body.textContent).not.toContain("onerror");
    expect(screen.getByText(/Another deterministic constraint/)).toBeTruthy();
    expect(document.querySelector("img")).toBeNull();
  });
  it.each([{ version: 2 }, { candidate_sha256: "SECRET_PASSWORD" }, { candidate_bytes: -1 },
    { diagnostics: Array(65).fill(projection.diagnostics[0]) }, { lot_count: 4097 }])("rejects malformed projection %j", change => {
    render(<PlanAdmissionPanel diagnostic={{ ...projection, ...change }} />);
    expect(screen.getByRole("status").textContent).toBe("Diagnostic unavailable or incompatible version");
    expect(document.body.textContent).not.toContain("SECRET_PASSWORD");
  });
  it("distinguishes missing capture and unknown admission, not success", () => {
    render(<PlanAdmissionPanel diagnostic={{ ...projection, status: "not_verified", candidate_sha256: null,
      candidate_bytes: null, candidate_available: false, capture_complete: false }} />);
    expect(screen.getByRole("status").textContent).toBe("Admission not verified");
    expect(screen.getByText(/Private capture incomplete/)).toBeTruthy();
  });
  it("has no empty panel before any admission", () => {
    const { container } = render(<PlanAdmissionPanel />); expect(container.firstChild).toBeNull();
  });
});
