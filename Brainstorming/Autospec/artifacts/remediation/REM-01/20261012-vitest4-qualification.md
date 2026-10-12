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
