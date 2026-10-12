# Exact native delivery clocks

`NativeTimingRecorder.ingest_delivery(receipt, source_proof, *, source_root)`
accepts the exact raw V1 delivery receipt present in an intact supervisor X.
It rechecks source, manifests/locks, trusted recipes, environment attestations,
and current immutable Docker identities through `delivery_build_checks`.
All predicates must be true before clocks are retained.

The admitted paths are `backend_dependency.timing` (install),
`frontend_build.dependency.timing` (install), `frontend_build.timing` (build),
and the unique `commands[kind=image_build].timing` (docker). The backend-only
case admits its two real clocks. Their copies in builder/command receipts must
match exactly. Cache/layer preparation clocks retain rc=null for the install,
never a fictitious uv/npm exit. Bounds must be zoned, seconds finite and
nonnegative, and each native subclock is ingested once even with another X
wrapper around identical receipt bytes. No phases are appended after a partial
validation failure. Generic split execution ingestion now also rejects repeats.

For the five diagnostic phases, ingest suite `environment_preparation` and
`timing` via `ingest`, record the actual browser operation via `measure`, and
call `ingest_delivery` for delivery. Do not additionally time the encompassing
`build_delivery_image` as a build phase: that would mix install/build/docker.
Phase totals are diagnostic elapsed operation sums, not an asserted exclusive
global wall-clock budget. In particular, browser context lifetime must not be
silently advertised as exclusive browser CPU work.

Native run: `delivery-timing-native-junit.xml`, **16 PASS / 13.53s**, including
real locked Linux cache preparation, tsc/Vite, final image inspection and exact
four-clock ingestion. `native-timing-evidence/delivery-clocks` retains untouched
native receipts and clock X files. Offline adversarial cases cover stale raw,
source/image drift, failed build, altered redundant copy, missing/wrong-phase
clock, negative/NaN/boolean seconds, unzoned/reversed bounds, duplicate input,
and a complete five-phase composition. These are independent synthetic fixture
identities, not product acceptance or a REM-25 campaign.
