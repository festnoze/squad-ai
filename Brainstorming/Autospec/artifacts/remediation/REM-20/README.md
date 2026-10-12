# REM-20 native evidence handoff

Source API checkpoint: `c9e762e0`. Production host fallback correction is a
separate commit `08996702`. Only independent synthetic fixture campaigns were
run; no paid LLM generation, REM-25 benchmark run, user database or historical
snapshot was modified.

Final run (`delivery-final-native-junit.xml`): **30 passed, 67.87s**, with both
real-Linux opt-ins. Includes actual locked Python/Node dependencies and audit,
TypeScript+Vite build, immutable delivery/cache image inspections, README CLI
in fresh Linux NETNONE, real Argon2/SQLite explicit fixtures, nominal and
deliberately failing reproduction. Node vulnerable fixture yields real
advisories and rc1; it is **not** classified as production-exploitable without
an independent source review. No raw audit exception became an empty PASS.

Latest units (`final-unit-junit.xml`): **63 passed, 9 explicit opt-in
skipped, 1.80s**. The added two npm-native cases account for the extra opt-ins;
both were executed in the 30-PASS native run. No critical product test was
skipped or transformed. Earlier
native/README/unit JUnits are retained, including `readme-native-junit.xml`
with the rejected missing-pair test setup (2 FAIL, 1 PASS / 34.81s). Its paired
fixture setup was corrected and rerun, not the fail-closed product rule.

`native-evidence/` contains untouched native JSON bytes plus metatest result
summaries. Raw receipts retain historical temporary paths, exact image IDs
and command clocks; they describe observation at execution time, not currently
running images or acceptance of a current support-client snapshot. Native X
files can be located by case-relative basename and re-hashed; metadata has not
been rewritten to pretend a different execution location. Source SHA and
contract `c…c` are synthetic independent-test identities, never the benchmark
oracle. No fixture passwords, sessions/cookies, user database, dependency tree
or product source were exported. JSON/XML Git conversion is disabled so native
SHA proofs remain byte-identical.

- `build`: real factory delivery receipt and every independent current-image /
  manifest-lock-recipe predicate observed at validation time.
- `python-audit`: real dated pip-audit 2.10.1 over exact public `idna==3.10` lock
  inventory; only pins/constant runner/Dockerfile entered networking context.
- `node-audit-good`: real dated npm audit of a no-dependency lock.
- `node-audit-bad`: real dated npm audit of deliberate `lodash==4.17.11` fixture;
  findings/rc1 retained and exploitability remains null pending independent R.
  This fixture is supported by the primary [Lodash advisory](https://github.com/advisories/GHSA-p6mc-m468-83gw),
  not a recommended dependency/version.
- `readme-good`/`readme-bad`: zero users before explicit fixture, actual isolated
  pytest CLI rc0, owned running launcher and seed; bad command's rc9 and false
  native proof retained. Their audit explicitly remains UNAVAILABLE, and their
  narrow obligations do not qualify as complete production OPS-05.

Audit CLI semantics were checked against the primary
[pip-audit documentation](https://github.com/pypa/pip-audit/blob/main/README.md)
and [npm audit documentation](https://docs.npmjs.com/cli/audit/).
Full production OPS-05 needs all reviewed README obligations, source-reviewed
expurgated config and a dated complete audit/classification. All 57 acceptance
IDs, all six E2E and the actual benchmark have **not** been declared PASS here.
