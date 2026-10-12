# REM-25 — canonical payload and narrowly guarded incident recovery

Author source: `439ebcfd2a3cc8950385bda3c763a2418d245439`, followed by review corrections `cd3a9d90c5b9cd7c991e93d4b69fcee8d2e1d44d`. Base: qualified factory `312cc2d38dc1a8ce7125243e4b3f36ac5ca03395`. Only launcher and launcher tests changed. No backend/frontend, API, pipeline, oracle, budget or product edits.

Canonical payload now supplies backend=python/framework=fastapi/frontend=react/database=sqlite/kind=fullstack/source=explicit. Brief, reference, 57 frozen IDs, source facts, seven-lot limit and estimated USD40 budget are unchanged.

## One-shot interface

Parent alone may run, after independent review and fresh qualification:

```text
python tools/support_benchmark_campaign.py --recover-bootstrap --campaign relais-support-rem25-20261012-final --project-id relais-support-rem25-20261012-fi-0e6ebc49 --expected-commit <qualified-clean-full-SHA> --port <free-approved-port>
```

Recovery is not a general retry/reset. Exact historical campaign/project, CREATED journal, original payload, state, monitor and oracle identities are required. Zero calls/tokens/cost/unreported usage and no fingerprint/stories/product files are admitted only for this known pre-bootstrap failure. The product directory must still contain exactly state+monitor; unknown files/directories, aliases/hardlinks, changed sources, old/unknown/dirty/cost-bearing cases are refused.

Fresh clean Git/source hashes, Linux Docker, Team/claude.ai/firstParty, Sonnet generation-only policy and all previous flags/settings checks remain. A durable exclusive `recovery-attempt.json` UNKNOWN is written before runtime writes/startup; separate `recovery-runtime/<UUID>` preserves original identity/log/input/admission/creation bytes. `recovery-dispatch.json` makes direct repeated dispatch impossible too. No second POST /projects or budget reset exists in this path.

Owned readiness/Job/retained interpreter checks precede GET original state, one PUT language=python, corrected PUT receipt and fresh GET/disk invariants, then one POST resume-build. `_persist` is asynchronous: only an exactly ORIGINAL disk state may lag an exactly corrected API state for a five-second read-only polling window, with all immutable evidence and product-file checks repeated. A different/partial state, changed API/usage/oracle/source, unknown files or timeout remain UNKNOWN/no POST/no retry. Each HTTP request retains the existing bounded 30-second transport timeout. Ambiguous resume is never retried.

Optional cooperative supervisor stop: write `{"action":"stop","project_id":"relais-support-rem25-20261012-fi-0e6ebc49"}` to the exact new runtime's `stop-intent.json`. It is checked between monitor iterations and exits through the retained Job/handle cleanup. This is not proof of graceful application shutdown. No PID/name lookup or broad process kill was added. The first incident had hard exec interruption and no finally receipt; none is invented.

## Evidence and limits

- `offline.xml` / `offline.log`: 105 PASS, 1.73 s, initial author corpus at439. Mock requests/processes only.
- `offline-async.xml` / log: 111 PASS, 2.10 s, bounded delayed/timeout/corrupt/changed state probes.
- `offline-v2.xml` / log: 115 PASS, 2.15 s, including exact prior monitor and contradictory PUT receipts. No skips.
- `incident-readonly.json`: actual incident bundle read only, 12 file hashes, original state b3e78ec1… and monitor3ab11c15…, zero complete usage, budget40, contract b6850a3f…, no recovery marker. No factory/API/provider/preflight-auth was invoked.
- Root's `continuation.md` was correctly refused as an unknown root file. Root moved it outside the campaign without deletion or whitelist exception, retaining hash6798bcc1…; only then did the actual read-only bundle pass.
- Initial development run had45 PASS/58 fixture setup errors: synthetic delivery_issues was mistakenly a string rather than its required list. The fixture typing was corrected; production state/guard was not relaxed.

Independent counter-review of439 preserved five RED findings in `C:/Dev/squad-ai/Brainstorming/Autospec/workspace/remediation-20261011/launcher-independent/recovery-red-v1.xml`: async persistence rejection, unknown agent monitor history, and three contradictory PUT receipts. All are addressed by cd3a9d90; its independent AFTER is the relecteur's responsibility, not an author R receipt.

This handoff does not assert successful recovery, paid generation, product conformity, all57 PASS, or new full-regression qualification. USD40 is an estimated budget, not a provider billing cap. Real factory startup, API mutation and generation remain exclusively the parent's later decision. No auth/Claude/inference/API call, campaign write or generated code execution occurred in this author work.
