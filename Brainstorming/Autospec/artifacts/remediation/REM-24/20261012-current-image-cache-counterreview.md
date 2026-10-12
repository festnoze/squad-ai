# Final report cache: historical build versus current artifact

Independent read-only parent counter-review of the cache introduced in
`b32d9f55` / integrated `88b79de1`. Parent held this section unchanged for the
counterexample. No pipeline/source file was modified by this reviewer.

All effects are trusted supervisor mocks and temporary inert fixture bytes:
NO Docker query, product execution, provider/model call, rebuild, or repair.
Synthetic X/R files are explicitly labelled mechanical historical fixtures,
not genuine product acceptance evidence.

`test_final_cache_current_image_counterreview.py` parametrizes an unavailable
image or changed CMD/identity, each against OPS-01 alone and OPS-01+OPS-05.
Existing report bytes, source/contract identities, current engine context and
source-review revalidation all match. The strict current-image port would refuse
if invoked. Builder, fact collection and verification ports reject any call.

Before correction: **4 FAIL, 0.86 s**,
`20261012-current-image-cache-before-v2.xml`. Every case observed
`admitted=True`, `delivery_ready=True`, final `PASS`; image-attestation calls=0,
source-review calls=1, rebuild/facts/verify/provider calls=0. Historical report
bytes remain intact. The raw assertions and captured JSON observations are in
the JUnit file; the test is unchanged for the after replay.

The first invocation selected this reviewer's older backend because pytest's
default import mode inserted its package root. That collection error is retained
as `20261012-current-image-cache-before.xml`, not labelled a counterexample PASS
or a production failure. The corrected command explicitly selects the parent's
backend in `PYTHONPATH`, runs trusted factory Python with `-P`, and uses pytest
`--import-mode=importlib`; only tests/artifacts in this reviewer's worktree are
written.

Recommended parent fix: before reusing cached PASS for any contract requiring
OPS-01/02/03/04, re-admit the exact immutable qualified image through
`load_qualified_delivery_image` (fresh ID/CMD/entrypoint/source label and receipt
checks). Absent/drifted image blocks current admission with NOT_VERIFIED/infra;
do not rebuild, call a model, delete, or rewrite the old historical proof files.
The helper `delivery_required` means OPS-05/README only, so it is not the correct
sole trigger for image availability.

These mocks establish a missing supervision call/invariant, not a native Docker
availability probe and not a global product verdict. Historical observations of
a successful build remain valid historical observations; they do not establish
availability of the delivery artifact now.
