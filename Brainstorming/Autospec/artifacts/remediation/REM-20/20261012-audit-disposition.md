# Audit disposition: source classification is not shipping permission

Frozen requirement OPS-05 remains unchanged: a critical/high exploitable defect
not arbitrated fails; an unavailable audit is NOT_VERIFIED. The former truthy
arbitration dictionary test could treat a refusal as permission. No business
requirement can be waived by these audit-only ports.

`arbitration` retains decision/owner/rationale/zoned date, and now requires an
explicit disposition (`accepted_risk`, `rejected`, `pending`) plus a real bool
`approved`. No default or string coercion is supplied. Rejected/pending,
unapproved accepted-risk, or exact `decision=deny_release|fix_required` produces
a false high-risk predicate. Unknown/missing/nonbool permission is unavailable,
never an invented acceptance. Known refusal takes precedence over a conflicting
accepted-risk label.

An accepted-risk/approved=true record additionally needs `approval: Proof R`
already supplied outside the producer. This module never creates it. Its exact
check is `OPS-05:accepted_risk:<audit_risk_subject(raw_finding,snapshot,contract)>`.
The dedicated file is bounded, unaliased, intact, within the supervisor root,
with exact advisory/source/oracle scope; its body has version=1,
kind=audit_risk_acceptance, authority=human, exact subject/snapshot_hash/
contract_hash, approved=true, authorized_by, rationale and a zoned date.
Classifier approved=true or an R issued by the source-review classifier alone
does not grant that permission. External approval provenance is the trusted
supervisor/human boundary, not a producer or model claim. The current campaign
has no supplied waiver: classifiers must leave arbitration=null for a known
high exploitable finding and cannot mint approval evidence.

APIs:

- `audit_arbitration_schema()` describes this reviewer protocol.
- `audit_risk_subject(raw_finding,snapshot_hash,contract_hash)` returns the exact
  human-approval subject SHA; it performs no writes or approval.
- `apply_audit_review(...)` rechecks classification and any provided waiver.
- `audit_disposition_checks(classified, *, evidence_root, snapshot_hash,
  contract_hash)` revalidates classification/raw/waiver bytes and returns the
  aggregate native predicate. It checks disposition only; the parent retains
  its dated native audit/tool/inventory/README/configuration gates.

Parent coordinator replaces the truthy arbitration dangerous-filter with
`checks.extend(audit_disposition_checks(audit,evidence_root=supervisor_root,
snapshot_hash=snapshot_hash,contract_hash=contract.contract_hash))`.
AdapterUnavailable means NOT_VERIFIED; returned false means FAIL. The parent
also supplies the protocol to its independent reviewer; no source-review prompt
or coordinator admission code was changed by this patch.

`audit-disposition-unit-v1.xml`: **75 PASS / 6 explicit native opt-in SKIP /
9.74s**, including existing documentation/review raccord. The added 23 cases
cover no arbitration, rejected/pending, deny/fix, contradictory labels, false/
missing/nonbool approval, accepted-risk without dedicated R, wrong human
authority, advisory/snapshot/contract drift, unscoped/string checks, missing date,
false proof and changed waiver bytes. The positive case is an explicitly
synthetic protocol fixture, NOT an actual human waiver or product acceptance.
No paid generation/audit, benchmark, source change or real waiver was created.
