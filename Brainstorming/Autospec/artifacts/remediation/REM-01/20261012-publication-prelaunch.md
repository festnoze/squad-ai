# Migration before plain-image launch

P1 counter-review corrected: the first publication implementation invoked the
reviewed migration after app startup. Apps whose startup requires a schema could
exit before it. Publication now prepares/attests its owned empty volume, journals
the migration UUID + pending state, runs EXACT reviewed argv in a temporary
same-image/same-volume NETNONE nonroot/readOnly container, cleans its exact daemon
identity, journals actual argv/rc/image/CID/volume/output hashes, then starts the
plain baked CMD (no runtime override or source overlay).

No command parameters/stdin are guessed. Only the reviewed ecosystem interpreter
is supported for this migration port. No fixture seed or recovery-time migration.
Failed/unknown migration preserves DB and blocks recovery. Its journaled temporary
UUID is available to bounded owned cleanup; an explicit stop then data destruction
is separate authorization, never automatic repair.

- Initial factory mocks: 30 PASS / 3 native excluded, 16.50 s (`20261012-publication-prelaunch-unit.xml`).
- Final factory mocks including interrupted migration daemon cleanup: **31 PASS / 4 native excluded, 14.21 s** (`20261012-publication-prelaunch-unit-v2.xml`). Pending migration blocks reprise, volume is preserved, app is never launched before a known successful migration.
- Real Linux probe: **1 PASS, 22.89 s** (`20261012-publication-prelaunch-native.xml`). Product startup opens SQLite in readonly mode and immediately queries the schema: it cannot create/seed/repair it. Explicit migration creates the empty table first. The actual plain image starts, health returns `{count:0}`, stop/restart preserves schema and does NOT rerun non-idempotent CREATE TABLE.
- Raw native identities/configuration: `publication-prelaunch-native.json` (migration CID differs from runtime CID and is absent after exact cleanup).

Local supervisor/probes use the human's explicit permission. No product code ran
on the Windows host, no other project's resources changed, no paid provider call.
