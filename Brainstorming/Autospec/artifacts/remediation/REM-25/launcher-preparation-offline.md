# REM-25 — launcher prepare, not launched

2026-10-12. Base execution worktree fast-forwarded cleanly to d9b89375.
Only tools/support_benchmark_campaign.py, its offline test, and these REM-25
proofs changed. No backend/autospec, frontend or normative source edit.

## Contract and operation

Import is inert. --preflight performs read-only prerequisite checks and prints
an expurgated receipt; no runner construction, campaign directory or POST.
--launch repeats admission, exclusively creates a precisely named campaign
under C:/Dev/squad-ai/Brainstorming/Autospec/workspace, snapshots complete input,
and remains the foreground persistent owner of its fresh factory process.
Start that supervisor in a persistent parent-owned terminal, not a tool session
that may destroy its process tree when the turn ends. A detached independent
supervisor manager is not implemented here.

The future parent provides --expected-commit with the exact full clean qualified
factory/launcher commit, --campaign relais-support-rem25-<unique-name>, and port
8130 or another free loopback port. 18004 and 8126 are always forbidden.
This document is NOT authorization to run either real mode.

Preflight pins three exact raw SHA256 values, requires Docker Linux, examines
Claude --help and auth status --json only, and retains only loggedIn/authMethod/
apiProvider/subscriptionType. Team must be explicit (team, claude.ai,
firstParty). No account identifier or credential is serialized. Unsupported
CLI/auth shapes fail closed; parent must review the actual installed interface
before launch, without substituting inferred subscription information.

Factory environment is assembled before Autospec imports. Generation-only,
Claude Code and Sonnet are pinned, all phase/tier models Sonnet; routing,
escalation, fake, LLM review/evaluation, tracing and REM-23 lane are OFF.
Direct provider keys and token overrides are stripped. The installed dotenv
library lacks PYTHON_DOTENV_DISABLED support: fresh supervisor/child intercept
dotenv.load_dotenv before importing Autospec, without changing backend config.
Existing factory-to-CLI-to-product filtering and Docker NETNONE remain intact.
No product import or shell execution is added on the host.

The child re-attests clean Git identity and source hashes before imports and
requires GenerationOnlyRunner. Its started_at/source_stamp/PID attestation
must match loopback health and the owned process before any creation POST.
Windows Jobs helper assigns the factory while suspended and owns descendants.
Exit closes only that Job, no global stops or historical project cleanup.

Payload imports full specification/reference and reviewed source-only facts,
57 exact IDs, 56 mandatory/OPS-06 diagnostic, max_lots=7, fullstack and explicit
FastAPI/SQLite/React TypeScript Vite. Budget is 40 USD estimated subscription
usage, NOT a billing-account hard cap and not new provider credits.

A durable exclusive creation-attempt marker precedes the only POST; unknown
outcome is journaled and never retried. Campaign reuse is always refused,
including uncertain creation, so no automatic budget reset is possible.
The supervisor polls states and journals local review-request hashes. It never
approves reviews, edits the generated product, retries or resumes generation.
It retains ownership even when blocked/completed, until explicit interruption.

## Offline evidence and limitations

Command (execution worktree, PYTHONPATH=<that worktree>/backend):

    C:/Dev/squad-ai/Brainstorming/Autospec/workspace/remediation-20261011/factory-env/Scripts/python.exe -m pytest backend/tests/test_support_benchmark_campaign.py -q -p no:cacheprovider --basetemp=<new dedicated offline test temp> --junitxml=artifacts/remediation/REM-25/launcher-offline-v5.xml

v5: 32 PASS in 0.34 s. All external commands, Docker/Claude/auth and launched
factory process are mocked. No inference, provider use, account check or real
Docker/CLI command occurred. The nominal creation uses an inert request mock;
main launch and Windows Job lifecycle/readiness paths are separately simulated.

v1: 29 PASS / 1 FAIL (journal campaign keyword collision), fixed.
v2: 30 PASS before lifecycle additions.
v3: 30 PASS / 2 FAIL (process identity helper name), fixed.
v4: 30 PASS / 2 FAIL (subprocess omits CREATE_SUSPENDED constant), fixed with
the literal Win32 flag, matching existing helper conventions.
An initial sandbox pytest run could not create its default temp directory;
no tests ran. Reruns used explicit dedicated temp roots and approved file writes.
Raw historical receipts are retained; they do not describe product failures.

Needs independent source review, actual fresh admission by the parent, and an
explicit parent --launch AFTER qualification. No acceptance verdict or current
Claude Team authentication is claimed by these offline tests.
