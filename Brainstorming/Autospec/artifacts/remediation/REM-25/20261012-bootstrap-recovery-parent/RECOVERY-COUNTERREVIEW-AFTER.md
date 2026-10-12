# Canonical payload / same-project recovery AFTER

Reviewed corrected READY author revision
`cd3a9d90c5b9cd7c991e93d4b69fcee8d2e1d44d`, after
`439ebcfd2a3cc8950385bda3c763a2418d245439`, in rem25-bootstrap-recovery.
**122 PASS in3.07s**:115 current author launcher/recovery tests and7 independent
counter-tests. Receipt `recovery-after-v3.xml`; independent source
`test_recovery_counterreview.py`; original RED retained in `recovery-red-v1.xml`.
No remaining reproduced P0/P1 in this scoped offline recovery review.

## Reproduced gaps closed

- Metadata PUT returns exact corrected state before disk persistence converges.
  Read-only polling now admits only exact original or corrected disk while API
  remains corrected and every file/hash/state invariant is rechecked. No repeated
  PUT/POST. Corruption/new source/usage/oracle/file or timeout stays UNKNOWN/noPOST.
  A nominal delayed disk write now reaches one resume POST. The monotonic
  persistence deadline is5s; existing individual HTTP requests retain their30s
  timeout, so this is not a strict5-second entire network wall-clock cap.
- Exact historical build-monitor SHA is pinned, preventing an appended prior
  provider/unknown-usage event from being admitted as the known zero-call incident.
- The actual PUT response state is checked against the corrected whole state;
  wrong ID/budget/oracle is rejected before polling/resume even if a later GET
  might look favorable.

## Admission / dispatch / ownership scope

The canonical machine payload composes actual BackendLanguage/stack.resolve/
freeze without provider/bootstrap execution. No permissive public API label
normalization or backend policy change is introduced.

Recovery remains deliberately limited to the exact campaign/project/failure,
known initial payload/journal/state/monitor/oracle/source hashes, budget40 and
every zero-use token/call/cost field; exact allowed file inventory rejects other
project/code/unknown directories, aliases and unexpected artifacts. Existing
CREATED evidence is mandatory; creation ambiguity/reuse is not silently adopted.
The original input/creation/runtime log/identity bytes are not rewritten by the
new supervisor; journal prefix is retained and new runtime files are separately
owned. Language correction mutates only the allowed metadata, before the one
generation-resume authority boundary.

Exclusive fsynced UNKNOWN recovery intent precedes replacement factory launch,
and exclusive dispatch intent precedes any metadata HTTP. Exact one GET/PUT/
read-only convergence/POST sequence is bounded to the same project; ambiguous
resume is not retried and budget/oracle/run history are never reset. Default
launch retains clean-source/hash/env/Team/Linux/GenerationOnly/Sonnet/owned Job
admission and single-project creation guards. Retained interpreter liveness and
exact health matching precede dispatch. Author lifecycle tests preserve finally
Job/direct-child/interpreter cleanup on acknowledged resume/timeout; optional
stop intent is exact owned runtime +project identity only, never global/name/PID
cleanup.

This incident-specific supervisor is somewhat larger than a one-off manual PUT,
but its added code directly encodes the requested immutable admission, durable
ambiguity and owned-runtime constraints. No broader restart framework or new
product features are introduced; no further generic API normalization is needed.

## Raw receipts and limits

RED v1:5 FAIL/2 PASS in0.66s; three P1 findings documented separately.
AFTER v2:121 PASS/1 independent harness FAIL in3.25s. The newly reached final
assertion read UTF8 JSON through Windows-default read_text decoding; only that
read was corrected to json.loads(read_bytes), preserving the equality assertion.
AFTER v3:122 PASS in3.07s. Synthetic incident fixture gained an explicit monitor
hash pin; independent behavioral assertions were not weakened.

No actual campaign/API/provider/preflight/auth/Docker/factory startup/generated
product writes or execution occurred in this review. Tests use new dedicated
temporary incidents and inert HTTP/process doubles; author reports a separate
actual bundle read-only check, not actual resumed generation. Public canonical
contract, original incident and historical failure remain distinct evidence.

Root alone owns fresh qualified Team preflight and a single actual continuation
of the existing project after integration/review. This report grants no launch/
resume authority, proves no generated-product PASS, and does not replace root's
current composition/native readiness checks or matrix decision. No broad global
repeat was performed or requested here.
