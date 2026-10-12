# REM-06 — explicit clean pytest collection root

Code: `cc5be170`. Native replay: **24 passed / 20.91 seconds**, `native-v3.xml`.
No evaluator, parser, baseline, skip allowance, or acceptance expectation was
relaxed. The legacy trusted fixture command now supplies `--rootdir=.` and an
explicit discovery path `.` when running from the disposable run directory.

The retained global failure (read only) had a valid two-test PASS report, but
its root was `C:/Dev/squad-ai/Brainstorming`, with IDs rooted at
`Autospec/workspace/remediation-20261011/full-regression-third-snapshot/.../good-run/test_crypto.py`.
The independent baseline correctly required `test_crypto.py::test_hash` and
`test_crypto.py::test_smoke`, so strict admission rejected it. The fix binds
collection at command construction, never by stripping report-ID prefixes.

Two actual Argon2 integration variants now run under the original repository's
temporary subtree `workspace/remediation-20261011/collection-root-v3`, including
a synthetic nested ancestor `pytest.ini`. Each asserts exact IDs and report
root, real cryptographic hash/verify, a runtime-only environment without pytest,
and missing declared Argon2 still failing admission despite native importorskip
returning zero. Synthetic reports with `foreign-root/` IDs remain rejected even
though their basenames/functions and PASS counts match. Node clean-install,
environment/cache, and integrity countertests are in the same 24-case replay.

Historical diagnostics remain: v1 selected a nonexistent test filename (rc4,
no tests), corrected in the command only; v2 used an excessively deep worktree
artifact basetemp and failed before collection with Windows MAX_PATH / cwd267.
The fresh shorter v3 basetemp preserves nested-repository semantics without a
production path workaround or larger timeout. No existing fixture, historical
report, generated campaign snapshot, or user database was modified.

[pytest's primary rootdir documentation](https://docs.pytest.org/en/stable/reference/customize.html#finding-the-rootdir)
documents that node IDs derive from rootdir and that explicit path arguments
avoid external plugin-output paths influencing discovery. Rootdir is not a
Python import sandbox; production validation remains the owned Linux runner.
