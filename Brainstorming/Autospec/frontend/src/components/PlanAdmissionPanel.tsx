import { useId } from "react";
import { useI18n } from "../i18n/i18n";
import { planAdmissionPanel as labels } from "../i18n/messages/planAdmissionPanel";

type Diagnostic = { code: string; severity: "error" | "warning"; diagnostic_sha256: string };
export type PublicPlanAdmission = {
  version: 1; admission_version: 1; status: "pass" | "fail" | "not_verified";
  contract_hash: string; candidate_sha256: string | null; candidate_bytes: number | null;
  candidate_available: boolean; capture_complete: boolean; receipt_sha256: string | null;
  lot_count: number; diagnostics: Diagnostic[]; diagnostics_omitted: number;
};
const sha = (v: unknown): v is string => typeof v === "string" && /^[0-9a-f]{64}$/.test(v);
const bounded = (v: unknown, max: number): v is number => typeof v === "number" && Number.isInteger(v) && v >= 0 && v <= max;
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
    (!p.capture_complete || p.candidate_available) && bounded(p.lot_count, 4096) &&
    bounded(p.diagnostics_omitted, 8192) && Array.isArray(p.diagnostics) && p.diagnostics.length <= 64 &&
    p.diagnostics.every(d => d && typeof d.code === "string" && d.code.length <= 64 &&
      (d.severity === "error" || d.severity === "warning") && sha(d.diagnostic_sha256));
}

/** Isolated view. Parent supplies only the checkpointed public projection. */
export function PlanAdmissionPanel({ diagnostic }: { diagnostic?: unknown }) {
  const { lang } = useI18n();
  const id = useId();
  const text = (key: keyof typeof labels) => labels[key][lang];
  if (diagnostic == null) return null;
  if (!safe(diagnostic)) return <p role="status">{text("invalid")}</p>;
  const p = diagnostic;
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
    <ul>{p.diagnostics.map((d, i) => {
      const code = Object.prototype.hasOwnProperty.call(labels, d.code) && !["title", "fail", "pass", "not_verified"].includes(d.code)
        ? d.code as keyof typeof labels : "other_constraint";
      return <li key={`${d.diagnostic_sha256}-${i}`}><strong>{text(d.severity)}:</strong> {text(code)}</li>;
    })}</ul>
    {p.diagnostics_omitted > 0 && <p>{text("omitted")}: {p.diagnostics_omitted}</p>}
  </section>;
}
