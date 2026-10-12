# REM-14 — independent bootstrap browser counter-review

The source-only review of root `61442715` found one reproducible P1 false-green:
`_browser_preflight(... require_api=True)` accepted a literal HTML text
`Frontend → API → base de données : OK` without any frontend API request. A
real HTTP fixture and Chromium ran in distinct supervisor-owned NETNONE Docker
containers, using the exact RuntimeSession parent. No browser or product code
ran on the host. The actual fixture request ledger contained only `/`, `/`;
API calls were zero.

`literal-ok-counterexample.json` and `native-v2.xml` retain that observation.
The **1 passed / 14.98 seconds** metatest result means the old bug was reproduced;
it is NOT product or bootstrap acceptance. Source SHA at observation:
`dadb7fcb26e301c310c4304dcc0a308c6da3b676eeadd62c558d989d90f11971`.

The parent corrected the probe to observe a real same-origin GET `/api/health`
response during frontend navigation and compare its exact JSON to a supervisor
nonce-bound body. The follow-up negative regression supplies the valid expected
body and requires actual refusal plus an observed page request and zero API
calls. The parent selected `auto_navigate=False`, so only one navigation is now
expected. It does not count a missing-configuration guard as a rejection.

Historical diagnostics are retained: `native-v1.xml` failed because the trusted
test fixture omitted the HTML UTF-8 charset, fixed in the fixture only;
`native-v3-root-fix.xml` failed a too-specific timeout assertion because the
corrected probe instead rejected with an `observe_api: Error`. The v4 run
preserves the diagnostic with an obsolete two-navigation assertion. The parent
removed the preliminary harness navigation. `native-v5-single-navigation.xml`
now passes **1 test / 23.38 seconds** and `literal-ok-rejected.json` retains the
actual rejection and HTTP request ledger. This negative regression does not
itself prove the corrected nominal path works; the parent owns that positive
probe and its separate native receipts.

Other reviewed boundaries remain sound within their stated scope: no host
Chromium fallback, no client network exposure, no source/DB mount in the browser
container, an exact owned NETNONE parent, bounded outer browser probe, private
driver output withheld, and browser/controller/container cleanup on exit. Cold
browser-image preparation and cancellation cleanup timing are infrastructure
limits, not accepted business proof. The bootstrap probe is a narrow foundation
smoke, never acceptance for the 57 frozen requirements.

No root production file was edited by this reviewer, no paid generation was
called, and no historical campaign snapshot or user database was changed.
