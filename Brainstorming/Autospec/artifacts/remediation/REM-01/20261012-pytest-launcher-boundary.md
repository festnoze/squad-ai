# Trusted pytest startup: native red/green counterproof

No paid model call. Host runs only trusted factory tests. Product/adversarial
fixture bytes execute exclusively in owned hardened Linux Docker NETNONE.

## Confirmed counterexample

The old command `/opt/venv/bin/python -m pytest ...`, with `/app` as cwd, loads a
producer `pytest.py` instead of the installed runner. The fixture has
`business.answer() == 0` and a real test asserting `answer() == 1`. Its shadow
module never executes that test; it writes a fresh forged report with the same
node ID, `passed`, and a fabricated call phase.

Observed: **rc=0, report_valid=True, executed=1** and
`test_business.py::test_real=passed`. The regression correctly fails:
**1 FAIL / 1 excluded, 8.85 s**, `20261012-pytest-launcher-before-v2.xml`.
Exact image, source/environment fingerprints, actual argv and raw report are in
`pytest-launcher-before-v2/module-observed.json`. The first, weaker counterexample
with executed=0 is retained separately, not substituted for this stronger one.

## Closed vector and compatible behavior

The factory now executes `/usr/local/bin/python -I -S -c FACTORY_LAUNCHER ...`.
Before admitting product imports it explicitly adds the image-owned venv library
and `/opt/reporters`, imports pytest and its builtin plugins, imports the fixed
JSON/coverage plugins, verifies their resolved module origins, and loads the
locked asyncio plugin if that image has it. Arbitrary plugin autoload and
`PYTEST_PLUGINS`/`PYTEST_ADDOPTS` environment injection are disabled. `/app` is
appended only afterwards; `--import-mode=append` keeps pytest from moving product
test directories in front of dependencies. No runtime installation or fallback.

Both `pytest.py` and `pytest/__main__.py` are ignored as launchers: the actual
business test is collected and fails with rc=1. The exact collected ID is retained
unchanged; the real coverage export has the exact SHA-bound `business.py` inventory
and its executed line, not an invented total. The nominal Python/API NETNONE and
parameterized branch-coverage probes still pass. A native asynchronous test also
passes with staged malicious shadows of `pytest_jsonreport`, `pytest_cov`, and
`pytest_asyncio`, plus a staged `sitecustomize.py`; it asserts actual image-owned
module paths, exact collection ID, real execution, and coverage.

The wider replay initially found the old collection allowlist did not recognize
pytest-asyncio's actual `Coroutine` type (**60 PASS / 1 FAIL / 6 excluded, 66.13 s**).
Its raw rc=0/collected=1 report is retained in
`pytest-launcher-after-v2/async-incomplete-collection.json`. Only that exact native
type was added; unknown/custom types still fail. No node-ID suffix stripping.

Final replay: **61 PASS / 6 excluded, 86.36 s**,
`20261012-pytest-launcher-final-v2.xml`. This includes the same adversarial source
as the stronger red proof, both shadows with collection and coverage, trusted
asyncio, nominal native Python/API, and factory-only Linux/pipeline/Node coverage
regressions. Raw successful counterproof receipts are in
`pytest-launcher-after-v3/`; the earlier four-probe pass and intermediate failed
replay are retained without relabelling.

## Explicit limits

This closes producer working-directory substitution/startup precedence. It is
NOT a TEE or a sandbox between Python tests and business code in the same process.
Reviewed test/business code remains arbitrary code that can mutate Python objects
or emit dishonest reports; locked dependency trust, source review, immutable
checker baselines and independent supervisor probes remain necessary. Unsupported
custom plugins, missing reporter image paths, or unavailable Docker fail closed.
No protection against every malicious dependency wheel is asserted.

The flags and import behavior are documented by the primary sources:
[`-I` / `-S`, CPython 3.12](https://docs.python.org/3.12/using/cmdline.html),
[pytest plugin autoload controls](https://docs.pytest.org/en/stable/how-to/plugins.html#disabling-auto-loading-plugins),
and [pytest append import mode](https://docs.pytest.org/en/stable/explanation/pythonpath.html#import-modes).
