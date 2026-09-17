# Strategy discovery MVP, 2026-09-13

**D1-D4 delivered and verified on 2026-09-13.** Measured data, campaign outcomes, tests, strict replay
and browser evidence are recorded in [DISCOVERY_MVP_STATUS.md](DISCOVERY_MVP_STATUS.md). The next gate
is the signal-first research iteration described in
[POST_CAMPAIGN_REVIEW_2026-09-13.md](POST_CAMPAIGN_REVIEW_2026-09-13.md), following negative real results
and user feedback. The post-campaign Codex review and clock-horizon correction are delivered.

## Next milestones after feedback

**R1 delivered on 2026-09-14**, after adding the beginner tutorial and comparative charts. The real
fixed-protocol study has one descriptive candidate for replication and 27 inconclusive variants.
Measured evidence, conservative historical exclusions and missing-label bounds are in
[R1_RESULTS_2026-09-14.md](R1_RESULTS_2026-09-14.md). No demonstrated trading edge is claimed.

| Milestone | Scope | Decision evidence |
|---|---|---|
| R1 Signal study (delivered) | Verified 2024 H1 corpus, 28 fixed variants, tutorial and interactive charts | Real train-only result, exact-time missingness, distinct-market support, three-month readout and persistent exports |
| R2 Replication | Reproduce a bounded set of hypotheses before optimizing entry/exit | Multiple-testing accounting, costs/exposure sensitivity and a frozen later evaluation; insufficient support stays inconclusive |
| R3 Learned challenger | Add one regularized supervised model only if the features show replicated signal | Incremental performance over simple rules under the same data, costs and protocol |

Do not expand Optuna budgets, introduce RL, move to Forex or buy model infrastructure merely because
the initial finalists lost money. R2-R3 remain proposed work. R2 should first investigate high-price
calibration with rare-loss and censoring sensitivity, adequate support and a new untouched evaluation
period. The descriptive 90–100% bin had a 98.37% mean price; do not interpret it as proof that buying
at 90% is profitable. Preserve the R1 artifacts when revising historical protection or sampling.

The user resumed development towards the best cost/efficiency MVP after reviewing the data research
and the Hugging Face comparison. This is the active continuation after the delivered PLAN_MVP.md.
The fixed-agent workbench stays available. The new outcome is an end-to-end automatic discovery
campaign on substantially broader hourly Polymarket data, with visible uncertainty and reproducible
strategy decisions. A profitable strategy is not a delivery requirement or a promised result.

## Deliverables and completion evidence

| Phase | Deliverable | Required evidence |
|---|---|---|
| D1 Data | Pinned resumable archive acquisition, verified hourly corpus, retained censored-universe sidecars and quality report | Real files downloaded and verified; real dataset passes loader; measured dates/counts/exclusions, timestamp evidence and explicit fee scenario; no future labels in strategy features |
| D2 Search | Bounded Optuna parameter search plus symbolic rule discovery, isolated candidates using the existing simulator | Real campaign with varied decisions and persisted complete trial history; causal internal training windows; no sealed access; selected candidates only validated after selection |
| D3 Product | Campaign creation, progress/cancel, candidate rules/parameters/metrics, persisted history/export and finalist replay | Real API journey and browser test on delivered data, successful production build, restart reopening results |
| D4 Integrity | Time separation, no unavailable calendar features, meaningful uncertainty, correct costs and stable identity | Focused poisoning/accounting/statistical regressions, integration tests, lint/types, appropriate full suite and replay |

Use the public Polymarket archive already researched. Its v1 period and missing order books limit
external validity. Source availability, inferred technical lifecycle fields, unresolved markets,
unknown event relationships and simulated friction must remain explicit in data and UI. A settled
market adapter is a conditional research dataset, not a claim to reconstruct the whole tradable universe.

Search fits only on training data, logs every parameter trial and enumerated rule, and uses later
validation after freezing the finalists. Previously inspected validation is exploratory. Unknown
dependence between events is not counted as verified independence. Fewer than two resampling blocks
cannot promote a statistical claim. Each candidate receives independent initial capital/liquidity;
simultaneous competition remains a separately described experiment.

Default budget is 30 parameter trials, capped at 100, and a bounded symbolic search. Engine execution
and paper money stay local. RL, live orders, a new trading simulator, LLM signals and multi-asset
expansion remain unnecessary for this MVP. Learned models can join the same campaign later.

## Ownership

Root owns API/catalogue/service, CLI integration, dependency configuration, existing rule integrity
fixes, documentation and final verification. Astra discovery_engine owns optimizer, registry and
their focused tests. Astra polymarket_data owns the new archive importer/network helper/CLI and
focused tests. Sol discovery_frontend owns the web UI. Cross-file changes are coordinated.

## Scoped amendments

- Archive ingestion may write an archive-specific dataset using existing canonical writers and
  loader validation, without inventing taxonomy or passing historical coverage gates.
- `archive/` provenance, labels, universe and quality files enter the dataset hash. Existing datasets
  without that directory retain their hashes.
- Technical close dates inferred from settlement are not historically known expiry features.
  Archive strategies use causal tape features, and UI labels the date as an observed lifecycle boundary.
- `polymarket-research-2026-04` is an explicit 20 bp execution-fee scenario with a one-tick minimum
  half-spread. It is not an assertion about historical venue fees or a conservative upper bound.
- Optuna is allowed in optimizer orchestration. Engine arithmetic and fills remain integer and
  deterministic; networking stays in the existing importer boundary.
- Existing rule mining may expose an observation callback for every enumerated candidate, including
  rejects, so the research log accounts for all attempts.
- A first complete 2023 corpus can use verified daily objects plus an explicit CTF range projection.
  Every CTF event ID is checked against a retained, verified cutoff block timestamp; omitted groups
  must contain no earlier events. Ranges, footers, ETags, fragment hashes, projected files and cutoff
  evidence are retained and hashed. This is partial-object provenance, never full LFS verification.
  Full-object verification remains the default path when projection mode is not explicitly selected.

No required validation gate is waived by this amendment. Record measured evidence in
DISCOVERY_MVP_STATUS.md before declaring the goal achieved.
