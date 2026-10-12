# Independent native supervisor evidence review

2026-10-12; read-only review of `native_supervisor_probe.py` and the parent
receipt under `workspace/relais-support-rem25-native-supervisor-20261012-v2`.
Attested factory revision: `42bfd6e592f27af103eef36588a1ed8f572ceb69`, port8131.
Parent reported successful exit0 in5.97s. This reviewer did not execute the
helper, contact an endpoint, invoke Claude/auth/Docker, or modify parent files.

## What the helper and receipt substantiate

- Actual launcher admission runs before interception: clean exact qualified
  commit, three pinned source hashes, free allowed port, Docker Linux, mandatory
  installed CLI help interface and subscription auth metadata. No command mock
  replaces this preflight. Only four auth fields are retained: loggedIn=true,
  authMethod=claude.ai, apiProvider=firstParty, subscriptionType=team, checked at
  `2026-10-12T15:26:40.281593+00:00`. This is dated metadata, not perpetual account
  status or proof of a future provider call's funding/model.
- Popen is a subclass of the original native Popen, not a fake process. Actual
  suspended factory Job assignment, Job membership and retained actual interpreter
  handle are therefore exercised. Factory PID45492 and actual interpreter PID5352
  differ, substantiating the Windows venv redirector path. Their distinct retained
  creation identities are journaled. The member wrapper rechecks actual liveness.
- The real health callback permits GET `/api/health` only. Two attempts were
  recorded; successful admission traverses the launcher's exact started_at/
  loaded/current-source-stamp matching before obtaining the exact Job-member
  interpreter handle. The fixture intercept then independently asserts that one
  actual retained interpreter exists, its handle remains held and it is alive.
- Interception replaces create_once itself and throws before its body/POST.
  The helper cannot call the original creation function. The HTTP wrapper also
  rejects any non-health RPC. Exactly one intercepted boundary is recorded;
  no creation-attempt marker exists and projects is empty.
- Finally records FACTORY_OWNED, INTERPRETER_OWNED and SUPERVISOR_STOPPED, without
  OWNED_CLEANUP_ERROR. The retained interpreter handle is None after cleanup,
  process poll reports exit0, and a bounded socket connection fails after cleanup
  (`owned_port_closed=true`). Count assertions make these non-vacuous checks.

## Limits

The receipt does **not** substantiate project POST, project creation, generation,
Sonnet dispatch, cost accounting during inference, external review completion,
Docker generated-product execution or eventual mandatory acceptance. It is a
native trusted-factory ownership/readiness/interception/cleanup probe only.
It does not run an adversarial Windows process or prove cleanup of a generated
descendant tree; earlier offline containment tests remain a separate scope.
`project_created` is a marker-derived receipt field, not a remote-project query;
the stronger no-POST inference follows from the inspected interception and GET-only
wrapper, along with absence of generated local files.

Raw health response bytes are not retained; successful exact-health matching is
inferred from this trusted helper's successful branch through the inspected
launcher, not independently reconstructed from a network capture. CLI help is
likewise not retained, and only flag availability/auth metadata—not an actual
restricted inference—is exercised.

The first helper fixture attempt failed during asyncio's cold Popen subclass
import, before a factory process/project POST; parent corrected the fixture by
retaining Popen class semantics. That historical fixture error is not a launcher
product failure and is not omitted from the evidence history.

No new P0/P1 identified in this bounded helper/evidence review. Global5 remains
a separate release condition; a running/no-failure-yet partial global is not a
completed green regression. This note grants no launch authorization.

## Exact reviewed hashes

- helper SHA256 `a0a4991a6d4d0f4fab3fbc90009cbe37583da6eca0604edcc893bad74be45b0b`
- native-probe.json SHA256 `13e3d3f090a290b59535f44f625773207382a9d0a069b3c8bd6c6b3a64e001e2`
- supervisor.jsonl SHA256 `4b5c17746fb637e0b14ace4ace2bc0348962c4ac260200d9da7359a29ecc2ac5`
- factory-identity.json SHA256 `dc50c14523ba2f414f30ea5998f8d1706eab1a219593960e9a6ddbbe0f71b073`
