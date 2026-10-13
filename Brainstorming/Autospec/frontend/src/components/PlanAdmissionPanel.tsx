import { useId, useState } from "react";
import { useI18n } from "../i18n/i18n";
import { planAdmissionPanel as labels } from "../i18n/messages/planAdmissionPanel";

type Diagnostic = { code: string; severity: "error" | "warning"; diagnostic_sha256: string };
export type PublicPlanAdmission = {
  version: 1; admission_version: 1; status: "pass" | "fail" | "not_verified";
  contract_hash: string; candidate_sha256: string | null; candidate_bytes: number | null;
  candidate_available: boolean; capture_complete: boolean; receipt_sha256: string | null;
  lot_count: number; diagnostics: Diagnostic[]; diagnostic_counts: Record<string, number>;
  diagnostics_omitted: number;
};
const sha = (v: unknown): v is string => typeof v === "string" && /^[0-9a-f]{64}$/.test(v);
const bounded = (v: unknown, max: number): v is number => typeof v === "number" && Number.isInteger(v) && v >= 0 && v <= max;
const diagnosticCodes = new Set([
  "plan_json", "candidate_limit", "lot_definition", "lot_limit", "coverage", "source_invariant",
  "stack", "vertical_contract", "milestone", "dependency_pending", "dependency_graph", "file_claims",
  "shared_contract", "unresolved_finding", "review_unavailable", "plan_schema", "other_constraint",
]);
function safeCounts(value: unknown): value is Record<string, number> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const entries = Object.entries(value);
  return entries.length <= diagnosticCodes.size && entries.every(([code, count]) =>
    diagnosticCodes.has(code) && bounded(count, 8192));
}
function safe(v: unknown): v is PublicPlanAdmission {
  if (!v || typeof v !== "object") return false;
  const p = v as Partial<PublicPlanAdmission>;
  return p.version === 1 && p.admission_version === 1 &&
    (p.status === "pass" || p.status === "fail" || p.status === "not_verified") && sha(p.contract_hash) &&
    (p.candidate_sha256 === null || sha(p.candidate_sha256)) &&
    (p.receipt_sha256 === null || sha(p.receipt_sha256)) &&
    (p.candidate_bytes === null || bounded(p.candidate_bytes, 2147483647)) &&
    typeof p.capture_complete === "boolean" && typeof p.candidate_available === "boolean" &&
    p.candidate_available === (p.candidate_sha256 !== null) &&
    (p.candidate_sha256 === null) === (p.candidate_bytes === null) &&
    (!p.capture_complete || p.candidate_available) && bounded(p.lot_count, 4096) && safeCounts(p.diagnostic_counts) &&
    bounded(p.diagnostics_omitted, 8192) && Array.isArray(p.diagnostics) && p.diagnostics.length <= 64 &&
    p.diagnostics.every(d => d && typeof d.code === "string" && d.code.length <= 64 &&
      (d.severity === "error" || d.severity === "warning") && sha(d.diagnostic_sha256));
}

/** Isolated view. Parent supplies only the checkpointed public projection. */
export function PlanAdmissionPanel({ diagnostic }: { diagnostic?: unknown }) {
  const { lang } = useI18n();
  const id = useId();
  const [receiptCopyState, setReceiptCopyState] = useState<"idle" | "copied" | "unavailable">("idle");
  const text = (key: keyof typeof labels) => labels[key][lang];
  if (diagnostic == null) return null;
  if (!safe(diagnostic)) return <p role="status">{text("invalid")}</p>;
  const p = diagnostic;
  const copyReceiptReference = async () => {
    if (!p.receipt_sha256 || typeof navigator === "undefined" || !navigator.clipboard?.writeText) {
      setReceiptCopyState("unavailable");
      return;
    }
    try {
      await navigator.clipboard.writeText(p.receipt_sha256);
      setReceiptCopyState("copied");
    } catch {
      setReceiptCopyState("unavailable");
    }
  };
  const diagnosticCounts = Object.entries(p.diagnostic_counts).sort(([a], [b]) => a.localeCompare(b));
  return <section aria-labelledby={id} className="plan-review">
    <h3 id={id}>{text("title")}</h3>
    <p role="status">{text(p.status)}</p>
    <dl>
      <dt>{text("candidate")}</dt><dd style={{ overflowWrap: "anywhere" }}>{p.candidate_sha256 ?? text("missing")}</dd>
      <dt>{text("contract")}</dt><dd style={{ overflowWrap: "anywhere" }}>{p.contract_hash}</dd>
      <dt>{text("receipt")}</dt><dd style={{ overflowWrap: "anywhere" }}>{p.receipt_sha256 ?? text("missing")}</dd>
      <dt>{text("bytes")}</dt><dd>{p.candidate_bytes ?? text("missing")}</dd>
      <dt>{text("lots")}</dt><dd>{p.lot_count}</dd>
    </dl>
    {!p.capture_complete && <p>{text("partial")}</p>}
    {diagnosticCounts.length > 0 && <div>
      <h4>{text("diagnosticSummary")}</h4>
      <ul aria-label={text("diagnosticSummary")}>
        {diagnosticCounts.map(([code, count]) => <li key={code}>
          <strong>{text(code as keyof typeof labels)}</strong>: {count} {text("occurrences")}
        </li>)}
      </ul>
    </div>}
    <ul>{p.diagnostics.map((d, i) => {
      const code = (diagnosticCodes.has(d.code) ? d.code : "other_constraint") as keyof typeof labels;
      return <li key={`${d.diagnostic_sha256}-${i}`}><strong>{text(d.severity)}:</strong> {text(code)}</li>;
    })}</ul>
    {p.diagnostics_omitted > 0 && <p>{text("omitted")}: {p.diagnostics_omitted}</p>}
    {p.receipt_sha256 && <aside>
      <p>{text("receiptHelp")}</p>
      <button type="button" onClick={() => void copyReceiptReference()}>{text("copyReceiptReference")}</button>
      {receiptCopyState !== "idle" && <p role="status">{text(receiptCopyState === "copied" ? "receiptCopied" : "receiptCopyUnavailable")}</p>}
    </aside>}
  </section>;
}
