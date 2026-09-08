# PRD v3 : pmx, the trading agents optimizer

Extension of `docs/PRD_V2_HARD_OPTIMIZER.md`. v2 stays the base (data at scale, calendar engine, scripted
genomes, memory and hive, evolution, sealed claims, API and UI, live shadow book). v3 adds what turns
the arena into a professional strategy optimizer: market realism at scale, opportunity detection
(news lead, arbitrage, logical consistency, comparative analysis), learned agents trained on the GPU,
an adversarial market maker (the GAN), portfolio construction, and an end-to-end test that closes every
rung of the ladder. `docs/CONTRACTS_V2.md` remains the technical source of truth; every v3 interface is
added to it by an amendment package before implementation. `docs/PLAN_V3_WAVES.md` holds the waves.

Written 2026-09-07 after a short interview that fixed the intent below.

---

## 0. Confirmed intent

- **Outcome**: a professional optimizer of trading strategies on prediction markets, which discovers and
  measures real inefficiencies (news lead, cross-venue arbitrage and logical inconsistencies,
  comparative analysis) and breeds robust policies by evolution, reinforcement learning and small
  models trained on the GPU.
- **User**: the author, doing research, with a paper path toward real money later.
- **Why now**: v2 (contract plus the data wave) is in flight; the new ideas are added as later waves,
  not a rewrite.
- **Success**: on a sealed set of hundreds of real markets, at least one family beats the market after
  fees with a confidence interval, or the numbers prove that none does; every large feature is closed
  by an end-to-end CLI test on fixtures.
- **Constraints**: reality is the referee and the GAN is an adversarial market maker bounded by the real
  tape; the GPU is a 6 GB RTX 4050 (small transformers, QLoRA at 3B parameters at most); Polymarket is
  blocked in France; session quotas impose a wave-by-wave build.
- **Out of scope**: real trading, a simulator where agents make the price, an LLM as judge, large models.

---

## 1. Where v2 stands (2026-09-07)

- Wave 0 done: contract (2 879 lines, 85 rulings after three critics), five schemas now inside the
  package at `src/pmx/schemas/`, v1 frozen under `pmx.v1`, architecture and schema tests.
- Wave 1 landed but ungated: about 13 500 lines across types, errors, rng, journal, loader, schema,
  resample, builder, the Kalshi, Manifold, Polymarket and Metaculus importers, the news archive
  (Wikipedia current events and as-of revisions, Wayback, GDELT, Manifold comments, linker), the
  lexicons at `src/pmx/lexicons/`, the data CLI, the demo pack migrated to `data/demo_v1/` (12 markets,
  a manifest). Seven package test files exist. At least one seam defect is visible (`builder.py` calls a
  `hardness_tags_from_closes` that does not exist), which is exactly what gate G1 exists to fix. G1 has
  not run.
- Waves 2 to 6 (engine, agents, optimizer, surfaces, live) are specified and not started.

v3 changes one thing in those waves before they start: the execution model of E2 is built behind a
`LiquidityModel` protocol so that the adversarial market maker of rung 4 plugs in without touching the
engine, and the dataset carries event clusters (section 3.2) so the detectors of rung 2 have something
to compare.

---

## 2. The ladder

Each rung is a large feature with its own acceptance criteria and its own end-to-end test. A rung
starts only when the previous rung's end-to-end test is green, and every earlier end-to-end test stays
green (section 9).

| Rung | Feature | End-to-end test |
|---|---|---|
| 0 | v2 base: data, engine, agents, optimizer, surfaces, live | E2E-0 build, run, replay, claim on fixtures |
| 1 | Market realism at scale: universe, clusters, impact, liquidity protocol | E2E-1 three-venue cluster fixture, calibrated impact, replay |
| 2 | Opportunity detection: news lead, divergence, logic, comparison | E2E-2 planted anomalies found, nulls clean |
| 3 | Learned agents on the GPU: features, supervised floor, RL and ES policies | E2E-3 tiny policy learns a planted signal, exported, replayed |
| 4 | The adversarial market maker and stress scenarios | E2E-4 co-evolution stays in the envelope, robustness gap reported |
| 5 | Portfolio and meta-strategies, small LLM fine-tune | E2E-5 allocator beats its best member on validation fixture |
| 6 | Live extension: detectors and learned agents in the shadow book | E2E-6 daily job emits opportunities and hashed forecasts |

---

## 3. Rung 1 : market realism at scale

### 3.1 The universe

- Target size moves from hundreds to **thousands** of markets per twelve months: Kalshi's full settled
  universe in the window (politics, economics, climate and weather, sports, entertainment, science),
  Manifold's binary universe above the quality bar. The auto-generated multi-leg shards stay excluded.
- Universe statistics become a first-class artefact of the dataset: counts by provider, category, life
  length, liquidity decile, hardness tag, YES rate, and the market's own Brier by category (how good the
  crowd is where). These numbers are the denominator of every later claim.
- Hourly bars for liquid markets (median daily volume above a threshold) as a second dataset, per the
  one-grid-per-run rule.

### 3.2 Event clusters and logical structure

- **Cross-venue linking**: markets on the same real-world event across Kalshi, Manifold and, when a
  proxy makes it reachable, Polymarket are grouped into an `EventCluster` by a deterministic matcher:
  shared `wiki_subjects`, resolution dates within a tolerance, question similarity (token set ratio
  over normalised text), confirmed by a stored score and reviewable in the UI. False positives are a
  data defect, so the matcher is conservative and every cluster records why it matched.
- **Intra-venue structure**: Kalshi event tickers group mutually exclusive outcomes (the YES prices
  should sum to one) and threshold ladders ("above X by date d1", "above X by date d2") impose
  monotonicity; Manifold has explicit duplicate and complement markets. These relations are stored as
  `Constraint` records (`sum_to_one`, `implies`, `monotone_ladder`, `complement`) with the market ids
  involved.
- Both are computed at build time, sealed with the dataset, and never shown to agents as labels (an
  agent may see the cluster's other markets' prices, since a human would; it never sees a "this is an
  arbitrage" flag).

### 3.3 Execution realism v2

- **Decision latency**: an action decided on bar `t` executes at the open of bar `t+1`. There is no
  fill inside the bar the agent just observed.
- **Impact model calibrated from the tape**: per liquidity decile, the regression of the next-bar price
  change on signed volume gives an impact coefficient; a fill beyond the volume cap pays that impact.
  The calibration is a projection of the dataset, reproducible, and stored in the manifest.
- **Limit orders with queue position**: a resting order fills only after the observed volume at or
  through its price exceeds a queue estimate (a fraction of the bar's volume at that price).
- **The `LiquidityModel` protocol**: `quote(market, bar, side, size) -> Fill` and
  `on_bar_end(observed_flow)`. Three implementations: `historical` (v2's vwap plus cap plus slippage),
  `calibrated_impact` (this rung), `adversarial_mm` (rung 4). The engine calls the protocol and knows
  nothing else. The **envelope rule** applies to every implementation: the quoted spread never falls
  below the observed bid/ask when known, total fills never exceed the bar's real volume times the cap,
  and the fill price never leaves the bar's `[low, high]` range. Realism is a constraint, not a
  parameter.

### 3.4 Acceptance and E2E-1

- AC-11: a dataset of at least 1 000 Kalshi markets and 1 000 Manifold markets builds from the network
  (or the shortfall is documented), with universe statistics in the manifest.
- AC-12: clusters and constraints are computed on the real dataset; a sample of 30 clusters reviewed in
  the UI has no false positive.
- AC-13: the impact calibration is reproducible across two builds of the same raw data.
- **E2E-1** (`tests/e2e/test_e2e_1_realism.py`): from a fixture with two venues, one shared event and
  one ladder, `pmx data build` produces one cluster and two constraints, `pmx data stats` prints the
  universe table, a run with `liquidity=calibrated_impact` journals fills that respect the envelope, and
  `pmx replay` reproduces the hash.

---

## 4. Rung 2 : opportunity detection

Every detector is a deterministic projection of the dataset (prices, news, clusters, constraints) that
emits `OpportunityEvent` records with evidence and a measured ex-post payoff. Detectors are analysis,
not agents: they say which inefficiencies exist and how big they are, so that agents are built to
exploit measured edges rather than imagined ones. All statistics use the block bootstrap and the
permutation null of v2; a detector's headline number is a lower bound.

### 4.1 News lead (early signal from news)

- Event study around every linked `NewsItem`: the price path in windows before and after
  `visible_from`, per category and per link score. Reports pre-news drift (did the market move before
  the news was public, which is information leakage the agent cannot use) and post-news drift (did the
  price keep moving after publication, which is the exploitable lag).
- Headline features from the lexicons (direction, intensity, novelty versus the last seven days) are
  tested as predictors of post-news drift; the coefficient with its interval is the "news edge" of the
  category.
- Manifold comments get the same treatment, as a proxy for crowd chatter.

### 4.2 Cross-venue divergence (arbitrage)

- For every cluster, the price gap between venues over time: size, duration, half-life of reversion,
  and the gap net of both venues' fees and the spread envelope. An `arbitrage` event is a gap that
  exceeds the round-trip cost for at least `k` bars. The report says how often, how large, how long, and
  what a paper two-account book would have made under the latency rule.
- The play-money caveat is structural: a Kalshi versus Manifold gap is informative about Manifold's
  mispricing, not tradable for money; the report labels every pair by currency.

### 4.3 Logical inconsistency (Dutch books)

- `sum_to_one` violations (a set of mutually exclusive outcomes priced above or below one by more than
  costs), `implies` violations (P(A) above P(B) when A implies B), ladder non-monotonicity, complement
  mispricing. Each with the amount and the duration, and with the paper payoff of the risk-free
  combination.

### 4.4 Comparative analysis

- Favorite-longshot bias per venue, category and horizon (the calibration of the market itself).
- Autocorrelation of returns by horizon (momentum versus reversal), by liquidity decile.
- Calendar effects: weekend drift, hours to close, the last-day convergence pattern.
- Relative value inside a category: markets whose price departs from the category's realised base rate
  given their hardness tag.
- Volume and price: does volume predict direction or only variance.

### 4.5 Surfaces and E2E-2

- `pmx analyze <detector> --dataset <name>` writes `analysis/<dataset>/<detector>.json`; `pmx analyze all`
  writes the opportunity map. The UI gains an **Opportunities** tab: one card per detector with its
  lower bound, its interval, its null, and drill-down to the events on the market chart.
- AC-14: every detector runs on the real dataset and reports a lower bound, an interval and a
  permutation null; the shuffled-outcome null of every detector sits at or below zero.
- **E2E-2** (`tests/e2e/test_e2e_2_detectors.py`): a fixture plants exactly one cross-venue gap, one
  ladder violation and one news shock followed by drift; `pmx analyze all` finds each once, with the
  planted size within tolerance, and finds nothing on the same fixture with shuffled outcomes and
  shuffled news dates.

---

## 5. Rung 3 : learned agents on the GPU

### 5.1 Principles

- Training is impure and lives in `pmx/learn/`, outside the engine. A trained policy is exported as a
  weights file whose hash is the genome of a `torch_policy` agent family. Evaluation is the ordinary
  deterministic engine: the policy's outputs are quantised to ppm and integer positions before they
  reach the journal, so a run replays from its journal regardless of GPU nondeterminism.
- Only as-of data ever enters a feature. Text embeddings are computed at build time from as-of texts
  and stored in the dataset, so a policy cannot read the future through an encoder.
- Walk-forward only: train on fold `k`, validate on `k+1`, the sealed test once through `pmx claim`.
- Nothing outside `pmx/learn/` and `pmx/adversary/train/` imports torch. The architecture test enforces it.

### 5.2 Features

- `pmx/features/`: a deterministic integer feature vector per agent-visible market per bar: price and
  returns at several horizons, volume z-scores, time to close, category, cluster gap, constraint
  residuals, news counts and lexicon scores over windows, the market's own realised volatility, the
  agent's position and equity. Stored as integer arrays with a declared scale, with a float view for
  torch. The feature list is versioned and its hash enters the run manifest.
- Precomputed as-of text embeddings with a small sentence encoder (a MiniLM-class model, about 22 M
  parameters, trained before the window) for headlines and comments; stored per `NewsItem`.

### 5.3 The supervised floor

Before any reinforcement learning: logistic regression and gradient boosting from features to the
outcome (a calibrated probability) and to the forward price move (the price-move value). Their
walk-forward skill is the floor that every RL policy must beat to be worth its cost. These models are
cheap, interpretable, and often the end of the story.

### 5.4 Policy learning

- Environment: the pmx engine wrapped as a vectorised episodic environment over the dataset's training
  fold (one episode per market or per calendar window), rewards from the journaled PnL and Brier
  skill, costs from the fee schedule. Deterministic given a seed.
- Algorithms: PPO with generalised advantage estimation; evolution strategies (CMA-ES or OpenAI-ES)
  over policy weights, which parallelise well on CPU and pair naturally with the v2 evolution loop.
- Policies: MLP over the feature vector; GRU or a small transformer (under 5 M parameters) over a window
  of bars plus the news embeddings. All fit comfortably in 6 GB.
- Regularisation against the two classic failures: hold-out early stopping on the validation fold,
  and a turnover penalty so the policy does not learn to churn the paper book.
- Export: `pmx learn export <run> -> models/<hash>.pt` plus a JSON card (features version, training
  fold, seeds, validation metrics). The card is what the genome stores.

### 5.5 Acceptance and E2E-3

- AC-15: the supervised floor and at least one RL policy are trained on the real training fold and
  scored on validation with intervals; both are runnable as agents through the ordinary engine.
- AC-16: an exported policy's run replays to an identical hash on a second machine without a GPU.
- **E2E-3** (`tests/e2e/test_e2e_3_learn.py`): on a fixture with a planted exploitable news signal, a
  tiny policy trained on CPU for a bounded number of steps beats `market_follower` on the validation
  markets, is exported, runs as an agent, and replays; a control training on the fixture with shuffled
  outcomes does not beat the follower.

---

## 6. Rung 4 : the adversarial market maker (the GAN)

### 6.1 The idea

The traders are the discriminators; the market maker is the generator. The market maker controls the
liquidity the traders face, inside the envelope of the real tape, and is rewarded for reducing the
population's PnL. Alternating generations breed traders whose edge survives the hardest liquidity the
data allows, and a **robustness gap** (skill under historical liquidity minus skill under the
adversary) tells which edges were liquidity mirages.

### 6.2 Design

- `adversarial_mm` implements `LiquidityModel`: spreads, depth per price level, and impact as functions
  of the observed order flow and of the agent population's revealed behaviour (the hive's reputations,
  the recent flow). Parametric first (a genome of integer dials), then a small learned policy from
  rung 3's machinery.
- **Envelope, enforced by the engine**: the market maker cannot quote inside the observed bid/ask, cannot
  fill more than the bar's real volume times the cap, cannot fill outside `[low, high]`, and cannot see
  an agent's order before quoting it (quotes are set at bar open from information available then).
  An adversary that could rewrite the tape would make the score fiction; this one can only make the
  spread honest.
- **Co-evolution**: generation `g` of traders is evaluated against the market maker of generation `g`;
  the market maker's fitness is the negative of the population's bootstrap PnL; both sides mutate.
  The claim on the sealed test is made under both the historical and the adversarial liquidity, and the
  leaderboard shows both columns and the gap.
- **Stress scenarios, bounded by reality**: resampling which markets a run gets (market bootstrap),
  news dropout (hide a fraction of items), safety-lag jitter, fee shocks. No synthetic prices.

### 6.3 Acceptance and E2E-4

- AC-17: a co-evolution run on the real dataset reports the robustness gap per family with intervals.
- **E2E-4** (`tests/e2e/test_e2e_4_adversary.py`): three alternating generations on fixtures; every fill
  respects the envelope (asserted from the journal), population PnL under the adversary is at most the
  historical PnL, the gap is reported, and the run replays.

---

## 7. Rung 5 : portfolio, meta-strategies, small LLM fine-tune

- **Portfolio construction**: capital allocation across sub-strategies and detectors with
  correlation-aware sizing, a drawdown governor, and Kelly fractions bounded by the estimate's
  uncertainty (fractional Kelly on the lower bound).
- **Meta-agent**: a bandit over sub-strategies by rolling validation skill, with regime features from
  rung 2's comparative analysis.
- **Small LLM fine-tune** (optional, GPU): QLoRA on a 1 to 3 B open-weight model mapping as-of headline
  plus market context to a direction and confidence, trained on the training fold only, with the
  contamination rule of v2 applied by the base model's declared cutoff. It is one more `torch_policy`
  family and competes on the same board.
- **E2E-5** (`tests/e2e/test_e2e_5_portfolio.py`): on a fixture with three sub-strategies of known and
  different skill, the allocator beats its best member on validation and never exceeds the drawdown
  bound; replay holds.

---

## 8. Rung 6 : live extension

- The detectors run daily on open markets and emit hashed `OpportunityEvent`s before resolution; the
  learned agents and the adversarially selected champions forecast in the shadow book; a daily report
  summarises open opportunities, forecasts and realised scores.
- **E2E-6** (`tests/e2e/test_e2e_6_live.py`): with fixture "live" responses, the daily job emits
  opportunities and forecasts whose hashes are stable and whose later scoring equals the backtest path.

---

## 9. End-to-end testing discipline

- Every rung has one `tests/e2e/test_e2e_<n>_<name>.py` that drives the **CLI** (subprocess or the
  `main()` entry) on fixture datasets in a temporary directory and asserts artefacts, numbers and
  hashes. No mocks of pmx code; only the network is stubbed.
- E2E tests are ordered and cumulative: the gate of rung `n` runs `tests/e2e/` in full; a regression in
  E2E-1 blocks rung 4 as surely as a failing E2E-4.
- Each E2E fixture plants a known truth (a gap, a signal, a violation) and a null twin (shuffled), so a
  test proves both detection and non-detection.
- A nightly `pmx smoke --dataset y2026` runs the whole ladder on the real dataset with small
  populations and records numbers in `docs/BUILD_STATE.md`; it is not a test, it is the honesty log.

---

## 10. Architecture additions

```
src/pmx/
  data/clusters.py           EventCluster and Constraint matching (rung 1)
  data/embeddings.py         as-of text embeddings at build time (rung 3; torch behind an extra)
  engine/liquidity.py        LiquidityModel protocol, historical, calibrated_impact (rung 1)
  analysis/                  detectors: news_lead, divergence, logic, comparative, report (rung 2)
  features/                  versioned integer feature vectors, float view (rung 3)
  learn/                     env, ppo, es, policies, supervised floor, export, cards (rung 3)
  agents/families/torch_policy.py   the exported-policy family (rung 3)
  adversary/                 adversarial_mm, coevolution, stress scenarios, train/ (rung 4)
  portfolio/                 allocator, drawdown governor, meta bandit (rung 5)
  cli_analyze.py cli_learn.py cli_adversary.py cli_portfolio.py
tests/e2e/                   one file per rung
analysis/<dataset>/          detector outputs (git-ignored)
models/                      exported policies and cards (git-ignored, hashes tracked in claims)
```

Dependencies: `torch` (CUDA 12 wheel, CPU fallback), `scikit-learn` for the supervised floor,
`sentence-transformers` optional, all under a `learn` extra in `pyproject.toml`. The engine, scoring,
metrics and agents packages import none of them; `tests/test_architecture.py` gains that rule.

---

## 11. Risks specific to v3

| Risk | Mitigation |
|---|---|
| GPU nondeterminism breaks replay | Evaluation replays from the journal; training seeds are logged; the weights hash is the genome. |
| 6 GB VRAM | Policies under 5 M parameters, QLoRA at 3 B maximum, batch sizes in config, CPU fallback for tests. |
| Feature or embedding leakage | As-of is enforced at build time; embeddings computed from as-of texts only; the poisoned-future test is extended to features. |
| Detector multiple testing | Every detector reports a permutation null and a deflated bound; the opportunity map states how many detectors were run. |
| False cross-venue matches | Conservative matcher, stored reasons, UI review, a manual override file that is sealed with the dataset. |
| Manifold play money looks like alpha | Every number is labelled by currency; claims are per provider. |
| The adversary rewrites reality | The envelope is enforced by the engine and asserted in E2E-4; the adversary can only widen spreads inside what the tape shows. |
| Session quotas kill a build | One wave per workflow invocation; work lands on disk as it is written; gates resume. |

---

## 12. Acceptance criteria added by v3

AC-11 to AC-17 as stated in sections 3 to 6, plus:

- AC-18: `tests/e2e/` contains one green test per delivered rung and the gate of every rung runs them all.
- AC-19: the opportunity map on the real dataset is published in the UI with intervals and nulls.
- AC-20: `docs/BUILD_STATE.md` carries the nightly smoke numbers for every delivered rung, whatever their sign.

---

## 13. Revision history

- 1.0, 2026-09-07: written after the interview that confirmed the intent in section 0.
