# Factory frontend and bootstrap dependency check

The factory frontend upgrade passes. The Linux bootstrap upgrade is not yet
qualified: the first two native probes failed at npm lock resolution, before
tests/build/browser, as retained in `bootstrap-browser.xml` / `.log`. This is
not production security acceptance or an audit-risk waiver.

Follow-up npm profile: `22c5ca78`, with strict tool provisioning instead of a
peer bypass. Node22 remains immutable. A fixed npm11.6.4 tarball from the public
registry is checked against the saved primary SHA512 before extraction or tool
execution. Resolver networking receives only manifests, not `.env`, `.npmrc`,
producer source or scripts. The Node dependency recipe provisions the same
tool before the manifest COPY, and exposes its fixed path. Recipe version5 and
template hash invalidate old environment attestations; the schema's ten input
keys stay unchanged. Its native eight-case run passed in 82.27s: six metatests,
real Vitest4/Vite6 resolution/build and non-root NETNONE npm version observation,
and an actually wrong SRI refusing export while preserving the prior lock.
The exact lock of that native supervisor profile was audited separately:
rc0 / zero vulnerabilities across 92 dependencies, `npm-native/audit-native-profile.json`.

Vite6 follow-up `370e4e0a` keeps `.vite-temp` on `/tmp/vite-config-cache`, without
making dependencies writable. Its recipe hash changes the cache identity.
The isolated-runner owner supplies the corresponding tmpfs directory and
Vitest4 CLI/provider qualification. The first native npm receipt predates this
link and is explicitly a checkpoint for npm provisioning, not a new-template
delivery attestation. Unit profile/cache/lock/checker replay: 105 PASS / 16
explicit native SKIP / 3.81s; link follow-up: 90 PASS / 15 SKIP / 1.07s.
Complete React bootstrap nominal probes remain pending the coherent runner.

Chosen direct versions, verified on the public npm registry: Vite 6.4.4,
Vitest 4.1.11, React plugin 4.7.0. The combination fits their real peer ranges.
No `--force`, dependency override, application source change, or paid generation
is used. Vulnerable transitives are updated within their existing manifest
ranges. Browser and bootstrap fixture runs are reported separately.

Code: `b3ca6319` (parent cherry-pick `cf5542c5`). Factory verification:

- Public npm metadata / exact peer and engine ranges: `registry-metadata.json`.
- `npm ci --ignore-scripts --no-audit --no-fund`: rc0, 202 installed packages.
- `npm audit --json`: rc0, vulnerabilities `{}`, total 0 across 252 dependencies.
- 308 Vitest unit tests passed in 17.17s; JUnit `unit.xml`.
- TypeScript + actual Vite build passed; Vite build 1.42s. The existing 500kB
  chunk warning is retained, not silenced.
- Two existing factory Chromium/HTTP E2E scenarios passed in 2.1 minutes with
  FAKE_AGENTS=1; no paid generation. The interpreter and port-only configuration
  is retained; assertions, timeout, demo settings and cleanup remain unchanged.
- Bootstrap metatests: 44 passed / 15 explicit native opt-in skipped in 1.94s.
- Stabilized root4b5fa0dc + upgrade boundary replay: 60 passed / 15 explicit
  native opt-in skipped in 3.54s, `bootstrap-stable-boundary.xml`.
- Actual Linux bootstrap: **2 failed / 3 deselected in 183.35s**. npm10.9.9
  crashes resolving the admitted new manifest with `edgesOut`. Neither fixture
  published its frontend lockfile, so no generated-bootstrap lock audit is yet
  claimed. Factory Node24/npm11.6.4 success does not establish Linux support.
- Actual Vitest4 legacy-argument probe: rc1 `Unknown option --minWorkers`;
  retained counterexample log and sent to the isolated-validation owner.

Only three direct version pins changed: Vite 6.4.4, Vitest 4.1.11 and React
plugin 4.7.0. Targeted in-range transitive updates: baseline-browser-mapping
2.11.28, browserslist 4.29.3, form-data 4.0.6, nanoid 3.3.20, PostCSS 8.5.29,
source-map-js 1.2.2. No force or dependency override is present. The new lock
no longer includes tinypool or vite-node. The exact lock SHA256 is
`c52610725ecb292b4a5acf1739a7a5746e81c3938a26672303012f39d5301fec`;
manifest SHA256 `b39667876c259d39faaa3c75618eb2b9e63f05daf52da3b85121fcfd2071c102`.

Primary sources: [Vitest4 migration](https://v4.vitest.dev/guide/migration.html)
(Vite >=6, removal of tinypool), [Vite6.4.4 release](https://github.com/vitejs/vite/releases/tag/v6.4.4),
[Vitest4.1.11 release](https://github.com/vitest-dev/vitest/releases/tag/v4.1.11),
and the saved per-version public registry metadata. The probable npm resolver
cause is the primary [npm peer-edge fix #8448](https://github.com/npm/cli/pull/8448),
included in npm11.6.0; npm11.6.4 engine is `^20.17.0 || >=22.9.0` and supports
the existing Node22 toolchain. A separately attested resolver profile is being
coordinated, never a peer bypass. The two failure receipts remain historical.
