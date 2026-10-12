# Vitest 4 recipe qualification

Initial offline qualification: **22 PASS / 2 native cases excluded, 0.29 s**,
`20261012-vitest4-unit.xml`. This is recipe/preflight evidence, not native suite/coverage acceptance.

Only exact admitted versions 2.1.9 and 4.1.11 are supported. Manifest declarations,
lock CLI/provider versions, registry distribution URL and canonical sha512 SRI
must agree. The clean Linux `npm ci` phase verifies package bytes. Missing or
mismatched provider never causes a runtime install or host fallback.

Version 4 uses `--maxWorkers=1 --fileParallelism=false`, without `minWorkers`.
Coverage uses explicit source include/exclude and source-bound inventory, without
`coverage.all`; both removals are confirmed in the primary
[Vitest 4 migration guide](https://v4.vitest.dev/guide/migration.html).
Version 2 retains its separately proven flags for legacy fixtures only.

Native tests cover both versions and require untouched files in fresh coverage
despite a producer config trying to omit them. The v4 native replay initially
awaits the separately owned locked Linux npm11.6.4 toolchain remediation: npm10.9.9
has a confirmed resolver failure with the v4/Vite6 peer graph. No force,
legacy-peer-deps, dependency override or hidden installation is used to bypass it.
No paid model/provider call.

## Native outcome and retained counterexamples

- v1: 23 PASS / 1 FAIL, 218.71 s. Locked npm11 profile succeeds; Vite6 config loader attempts `.vite-temp` under immutable dependencies. Failclosed, not a coverage PASS.
- v2: 1 FAIL, 59.22 s. New attested image link `.vite-temp -> /tmp/vite-config-cache` plus runtime tmpfs directory fixes config loading. Real Vitest4 test rc0/PASS, but coverage admission rejects the new mapping shape.
- v3: 1 FAIL, 50.35 s. Raw fresh JSON retained externally and diagnostic shows missing `line`: AST-based V4 remapper emits the implicit else arm as `{start:{},end:{}}`. The actual counters include exercised and unexercised arms.
- v4 FINAL: **30 PASS, 95.36 s**, `20261012-vitest4-native-v4.xml`, including real locked Vitest2 AND Vitest4 suites/coverage, full source inventory including untouched module, hostile producer coverage config, genuine zero-hit missing lines, no stale JSON reuse, no host Node or runtime install.

Only the exact implicit-if-else V4 shape is admitted, after source-valid enclosing
if/line binding and matching explicit first location. Counters are preserved;
positions and zeros are not synthesized. Unknown/malformed/unanchored branches
remain refused. Raw diagnostics are written as coverage `.raw.json` outside the
producer tree, never treated as an independently accepted normalized report.
Recipe profile prerequisites: teammate commits `22c5ca78` and `370e4e0a`.
Dependencies `/opt` remain read-only; only the fixed configuration cache lives
in tmpfs. No models/provider billing calls occurred.
