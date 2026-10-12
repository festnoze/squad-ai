# Critical native baseline publication and QA provenance

Counter-review found a retry admission defect: a new `run_native` baseline was
saved before checking the shared protected checker hashes. A conflicting
candidate returned failure but remained saved; a subsequent same-owner run
could skip that conflict check and admit the weakened checker.

The corrected admission checks the protected map for **every** baseline,
including previously saved poisoned candidates. For a new baseline, it validates
the entire map before any publication, refuses an intervening owner's different
sealed IDs, publishes protection before the baseline, under the same supervisor
lock, and never overwrites a competing baseline. A saved baseline with absent
protection is unavailable rather than silently approved. These are fail-closed
states; restoring them requires explicit supervisor reconciliation.

QA helper provenance closes the naming-pattern gap without freezing all
business imports. The supervisor authorizer writes external
`qa-authored-files.json` with exact shape `{"files":["canonical/path.py"]}`
**before** QA mutations. The reader trusts no role, hash or producer annotation.
It bounds the journal to 2 MiB/20,000 unique canonical POSIX paths and uses
FileBroker to refuse links, junction/reparse points, hardlinks and escapes.
Workspace-relative entries are filtered by the exact factory frontend logical
prefix, then bound to present regular source files. Missing future files do not
receive invented identities. Existing QA-authored files are added to the first
baseline/protected map, even `checks/login_assertions.py` outside conventions.
An additional helper cannot silently extend an already sealed owner baseline.
Non-QA product implementation remains editable.

Parent raccord: writer role/owner must originate from supervisor context, and
the journal must be atomically maintained under a supervisor lock after normal
claims authorization. The reader API is
`read_qa_authored_files(supervisor, root, logical_prefix='')`. No fallback reads
producer metadata. No remediation is closed until that writer is integrated.

Proofs: initial baseline-only regression was 35 PASS/15.20s; first provenance
regression correctly exposed eight fresh-root fixture failures (38 PASS/8 FAIL,
17.79s), preserved in v2 JUnit. Fresh nonexistent canonical supervisor roots
now mean no provenance yet; real/aliased roots retain strict checks. Corrected
regression v3: 46 PASS/10.44s, with real Linux Docker native baseline/skip probe
active. All fake validator tests are offline admission mechanics; their source
strings are never imported or executed on Windows. No paid model/API call.

Final v5: **48 PASS/11.87s**, additionally proving no overwrite of a concurrent
owner's sealed IDs and refusal of an oversized provenance journal. The v4
attempt exposed and retained a test-fixture import indentation error before any
execution; the import was corrected. All five JUnit attempts are preserved.
