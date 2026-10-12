# Independent review checkpoint

Read-only parent review: `review_delivery.py` and `source_reviewer.py`; no
generation provider, source export, paid agent call or product command was run
by the review. The native audit runs before its independent assessment, so a
delivery plan/R is not required to query raw manifest advisory facts. Cached
raw receipts, source SHA and classification are rechecked; UNAVAILABLE remains
unavailable after an approval. Operational source R is not X/V or a global
acceptance verdict. Final acceptance still requires observed native predicates.

Found P1: a response originally named only source/contract/model/actor, allowing
an old independent approval to be resealed for a different operational subject
at the same source SHA. Parent fixed it with canonical request hash and stage
(including phase, trusted protocol, proposals and raw audit) plus exact delivery
and audit subject fingerprints. Independent probes now change phase, stage,
runtime proposal, raw audit and trusted protocol while retaining source SHA;
they also attempt to reuse a delivery approval after a changed documented argv.
These tests use explicit synthetic reviews, never real product qualifications.

Reviewed fixed source hashes:

- `review_delivery.py`: d032b2ac177f542450c8fbea25b7630076aa4b8040478c418cf6e577ed323471
- `source_reviewer.py`: e01846074aca797f2d841c79d10772f7a1a76779c1c27219d9c2e6cc6a6c5b9d

Also diagnosed six original full-suite failures. Three rollback metatests
claimed a Git checkpoint without an owned `.git` marker/root read. Fixtures now
model those facts and exercise the real ownership check. Manifest union now
observes the explicit Linux resolver port and staging of the returned lock;
its synthetic resolver is not an installed dependency proof. The semantic and
scope tests were not weakened: they found real production omissions of
`revert` and `merge-base` from the hermetic Git command set. Both are admitted
only as strict internal local forms; symbolic revert HEAD is pinned to an
immutable SHA before mutation. Hook/filter/config/network refusals remain.

`legacy-owned-checkpoints.xml`: 4 PASS / 4.02s against parent production with
only coherent mocks. `legacy-git-boundary-v2.xml`: 40 PASS / 35.03s including
all six originally failing tests, dangerous argv refusals, and real local
merge/revert in an owned temporary Git repo. The full global suite has not been
rerun or declared green here. No user repository reset/clean was executed.

Native timing ports and proofs are documented separately under REM-20. Those
elapsed phase sums are diagnostics, not fabricated process rc or an exclusive
global wall-clock budget. Final baked command evidence is checked against
source-reviewed argv, exact trusted recipe and Config.Cmd/Entrypoint, not a
RuntimeSession command override. The new parent pipeline/delivery raccord is
outside this initial read-only review checkpoint and requires its own review.
