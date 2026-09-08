# Review of 2026-09-09 : scale, recency and a tag taxonomy that supports comparison

Three requirements raised by the user after looking at the running interface: the panel shows twelve
example markets and that is far too few to test agents; only recently resolved markets should be used, so
that a model cannot already know the answer, while landmark older events are kept apart rather than
thrown away; and every market should carry tags, so that markets can be sorted and so that comparative
analysis runs on markets of the same nature.

This file records the decisions D-S1 to D-S9 and where each one lands. It continues
`docs/REVIEW_2026-09-08.md` (decisions D-R1 to D-R14) and is carried into the build by part 4 of
`docs/PLAN_V3_WAVES.md`.

## What was measured first

Counted on the tree of 2026-09-09, before any decision:

| Quantity | Value |
|---|---|
| markets the interface actually shows | 12, from `data/demo_v1/markets/` |
| what those twelve are | Brexit 2016, Trump 2016, Trump 2024, BTC 60k 2021, BTC 100k 2022, the Fed hike of March 2022, the ETH merge, GPT-4, LK-99, the Titan submersible, Argentina at the 2022 World Cup, the 2023 US recession |
| markets in the sealed research dataset `data/datasets/y2026` | 287 (220 Kalshi, 67 Manifold) |
| distinct values of `tags` over those 287 markets | 201 |
| most frequent tags | `kxbtcmaxmon` 16, `kxaaagasm` 13, `economics-default` 12, `crypto-speculation` 11, `technology-default` 11, `kxgoldw` 9, `bitcoin` 9, `kxbrentw` 8, `world-default` 8 |
| markets whose tag list merely repeats their category | 58 of 287 |
| categories (a closed 12-value vocabulary, populated) | finance 59, economics 57, politics 40, crypto 38, weather 30, tech 27, other 20, world 8, sports 5, entertainment 2, science 1 |
| cells of `category x horizon` holding at least 30 markets | **2 of 31** |

Two readings follow, and they decide the shape of the work.

First, the interface is not showing a sample of the research dataset: it is reading the v1 demo pack,
which is a separate twelve-market artefact. The user's twelve are therefore not a truncation of the
287, they are a different thing, and the twelve happen to be exactly the landmark events the user asked
to keep in a category of their own.

Second, `tags` is a raw dump of provider labels. A field whose most frequent value is a Kalshi series
ticker appearing sixteen times cannot group markets for comparison. Worse, the coarsest useful grouping
that exists today, category crossed with horizon, already puts only two of thirty-one cells above thirty
markets. Adding the question's shape, which is what actually decides whether two markets are comparable,
multiplies the cells by about eight. At 287 markets almost every group would be empty. The requirement
for thousands of resolved markets is therefore not a matter of taste: it is what a comparison at cohort
level costs.

## A. Scale, and an interface that shows it

| # | Decision | Lands in |
|---|---|---|
| D-S1 | (**Corrected by D-S11 and D-S12 below: the target differs per venue and the market floor is about 7 000, not 2 000.**) The research dataset's build target is stated **in cohorts, not in markets**: at least **40 usable cohorts per venue**, a cohort being usable at `n_train >= 30` (D-S6). The market count is whatever that takes, which the arithmetic above puts in the thousands: decision D-R7's 2 000 per venue is restated as a **floor**, not a target, and the per-provider cap stays lifted. A build that reaches the market floor but not the cohort floor is a failed build and says so in the manifest. | Contract 7.4 and 12.7 (amendment C1c); package DS1; gate G3; **AC-32** |
| D-S2 | The interface **never reads the demo pack by default**. The API and the market view serve the sealed research dataset, with server-side paging, and the demo pack is reachable only through an explicit dataset selector that labels it. The twelve-market panel disappears as a default the moment U1 and U2 land. | Packages U1 and U2 (lot 5b); **AC-32** |

## B. Recency, and the landmark events kept apart

| # | Decision | Lands in |
|---|---|---|
| D-S3 | The one-year window of contract 5.6 becomes explicit and bounded: `window_days` defaults to 365, is refused above **730**, and the contract states the two reasons in the normative text so that no operator widens it with a flag (a model's knowledge cutoff makes an older resolution a possible recall rather than a forecast, and a regime three years old is not the regime being traded). Every manifest records `window_days` and the true resolution span; a leaderboard row from a dataset with `window_days > 365` carries the label. | Contract 5.6 and 7.4 (C1c); `BuildConfig`; DS1; **AC-33** |
| D-S4 | The landmark events are kept, in a **quarantined partition** rather than as an exemption. The dataset manifest gains `purpose: "research" \| "showcase"`, which replaces the ad hoc `Dataset.is_demo_pack` property (unsealed, provider `demo`). A showcase dataset is exempt from the window rule and **sealed like any other**, so it replays by hash; it is **never** the source of a fold, a fitness value, a rule promotion, a hive insight or a claim, and the optimizer, the rule tester and the claims ledger refuse it with a named error rather than a silent skip. The interface may show it, labelled `showcase`, next to the research dataset. | Contract 5.6, 7.1, 12.7 (C1c); `pmx.types`, loader, DS2; O1, O2, O4, S2; **AC-33** |
| D-S5 | The showcase pack grows past twelve. It is built from the events worth demonstrating on (an election, a central-bank surprise, a crypto threshold, a technology release, a scientific claim that collapsed, a sporting upset) wherever a real tape survives in the Wayback archive or in Manifold's history, and it carries the same bars, trades, news and as-of stamps as a research market, because a showcase whose data is shallower than the research data teaches the wrong lesson about the product. Target a few dozen; document what could not be sourced. | Package DS2 (lot 5b); gate G3 |

## C. Tags that can carry a comparison

| # | Decision | Lands in |
|---|---|---|
| D-S6 | `tags` becomes a **controlled vocabulary** shipped as `src/pmx/lexicons/tags.v1.json`, and the builder refuses a value outside it. The raw provider strings move to a new field **`provider_labels`** (same pattern, kept verbatim, never a cohort key, never displayed as a tag). The vocabulary has **three facets**, and every market carries all three: `subject`, one or more, the fine topic under the category (`elections-us`, `central-bank-rates`, `cpi-inflation`, `employment`, `oil`, `gold`, `equity-index`, `fx-major`, `bitcoin`, `ai-models`, `spaceflight`, `epidemics`, `temperature`, `storms`, `court-rulings`, `armed-conflict`, and so on); `structure`, exactly one, the question's shape, which is what decides whether two markets are comparable at all (`threshold-above`, `threshold-below`, `range-band`, `by-date`, `count-over-period`, `head-to-head`, `multi-outcome-leg`, `recurring-series-leg`); `horizon`, exactly one, derived from the market's life in bars and never from provider text (`intraday`, `week`, `month`, `quarter`, `year-plus`). | Contract 7.2 and a new 7.14 (C1c); `market.v2.json`; the `market_listed` journal event; DS2 |
| D-S7 | The **cohort** becomes a first-class object: `Cohort(id, category, subject, structure, horizon, provider, n_train, n_validation, n_sealed)`, listed by the builder into the manifest and by the loader into the dataset, usable at `n_train >= 30`. It is the unit of comparative analysis: detector R2d runs per cohort, the calibrator agent family becomes per cohort instead of per category, a rule's `scope` gains `cohorts` alongside its kinds, providers, categories and tags, and leaderboards and claims gain per-cohort rows carrying their own intervals and their own candidate count for deflation. A cohort claim below the usable size is refused, not weakened. | Contract 12.3, 12.6, 12.7 and 18 (C1c); DS2, S2, R2d, A-family, O4, U3 |
| D-S8 | The tagger is **deterministic and auditable, never a model call**: a sealed provider mapping first (a Kalshi series to facets map extending `kalshi_series_categories.v1.json`), then keyword rules over the question text drawn from the shipped vocabulary, then an explicit `other` with a counter. No network, byte-identical across rebuilds, and the mapping files enter the sealed dataset hash. The reason is that a tag decides which cohort a market lands in, so a tag that moved between two rebuilds would move a claim. | DS2; contract 7.14 (C1c) |
| D-S9 | (**Corrected by D-S14 below: the threshold is per venue, 90 percent, not a single 95.**) Coverage is **measured and labelled**, exactly as decision D-R4 labels weak news links. The manifest records, per facet, the share of markets carrying a value, the number of distinct values, the cohort size distribution and the count of usable cohorts. A build where fewer than 95 percent of markets carry a subject facet, or where fewer than 10 cohorts reach the usable size, is labelled `taxonomy: "weak"` in every leaderboard and every chart that groups by tag. A **manual audit of 50 random taggings** per build is stored as `audit/taxonomy_<hash>.json` with the reviewer's verdicts, and the manifest reports the precision. | DS2, gate G3; **AC-34** |

## D. The interface that uses all of it

| # | Decision | Lands in |
|---|---|---|
| D-S10 | The market view becomes a **browsable index over thousands of markets**: server-side paging, filters on category, each of the three facets, provider, fold, hardness tag and outcome, sorting on resolution date, life, volume and final price, and a **cohort view** that puts the markets of one cohort side by side with each agent's calibration on that cohort. The guided tour of package U5 gains a chapter on the cohort view. | Packages U2 and U3 (lots 5b and 7), U5 (lot 7); **AC-34** |

## E. New acceptance criteria

* **AC-32 Scale**: the sealed research dataset reaches at least 40 usable cohorts per venue (`n_train >= 30`) and at least 2 000 resolved markets per venue, or the manifest and `docs/BUILD_STATE.md` state the shortfall per filter; the interface lists them with paging and never defaults to the demo pack. This **supersedes AC-11** of `docs/PRD_V3_TRADING_OPTIMIZER.md`, which asked for 1 000 markets per venue and said nothing about cohorts; amendment C1c corrects AC-11 in place so the two documents do not disagree.
* **AC-33 Recency and quarantine**: every market of a `purpose: "research"` dataset resolved inside `window_days` of the freeze, `window_days` refused above 730; the `purpose: "showcase"` pack holds the landmark events, seals and replays by hash, and the optimizer, the rule tester and the claims ledger each refuse it with a named error proved by a test.
* **AC-34 Taxonomy and cohorts**: every market carries at least one `subject`, exactly one `structure` and exactly one `horizon` from the shipped vocabulary, or is counted in the `other` bucket; `tags` outside the vocabulary is refused; the manifest reports per-facet coverage, the cohort size distribution and the taxonomy audit's precision; the market view filters on every facet and the cohort view shows per-cohort calibration.

## G. Measured on 2026-09-09 : what a prototype tagger says, and the four corrections it forces

Decisions D-S1 to D-S10 were written from the shape of the data. Before amendment C1c turns them into
normative text, a prototype deterministic tagger was run over the 287 markets of `data/datasets/y2026`:
thirteen ordered regular expressions for the `structure` facet, thirty keyword rules for the `subject`
facet, and the `horizon` facet derived from the market's life. The point was to find out whether the
targets are reachable before the contract states them. They are not, as written, and the corrections are
below.

| Measurement | Kalshi | Manifold |
|---|---|---|
| markets | 220 | 67 |
| `subject` coverage from a first-pass vocabulary | 80.0 percent | 64.2 percent |
| `structure` coverage | 87.7 percent | 49.3 percent |
| distinct subjects seen | 20 | 15 |
| non-empty cohorts (both venues) | 102 | |
| cohort size histogram (both venues) | 58 of size 1, 20 of 2 to 4, 18 of 5 to 9, 6 of 10 to 29, **0 of 30 or more** | |
| cohorts reaching 10 markets | 6 | **0** |
| cohorts reaching 30 markets | **0** | **0** |
| of the 6 cohorts reaching 10, how many sit entirely in one fold | **6 of 6** | |
| markets implied for 40 usable cohorts at `n_train >= 30` | **about 7 300** | not reachable on this distribution |

The largest cohorts found are `bitcoin / threshold-above / month` at 16, `gold-silver / threshold-above /
week` at 15, `gas-prices / threshold-above / month` at 12 and `oil / threshold-above / week` at 11, all on
Kalshi. Kalshi's questions are heavily templated ("Will the gold close price be above 4451.99 USD/t.oz on
August 31, 2026 at 5:00 PM EDT?"), which is why a deterministic tagger reaches 88 percent on the structure
facet with thirteen rules. Manifold's are not: the untagged tail is genuinely unbounded (a Chainsaw Man
announcement, a Fooming Shoggoths song, the word count of a papal encyclical, the Scottish league), and it
also contains self-referential markets ("Will this market be above 50 percent when it closes?", "Do you
like 4 percent odds?") which are not forecasts of the world at all.

| # | Correction | Lands in |
|---|---|---|
| D-S11 | **The cohort target is not the same on both venues, and D-S1's single number is withdrawn.** Kalshi carries the comparison: at least **40 usable cohorts**. Manifold reaches **zero** cohorts of ten today and its question distribution has no dense templates to concentrate, so its target is **8 usable cohorts** and its stated role is breadth and print-tape depth, not comparative analysis. A gate that finds Manifold below 8 records it and does not fail the build; a gate that finds Kalshi below 40 fails it. | Contract 7.4 and 12.7 (C1c); DS1; gate G3; AC-32 restated |
| D-S12 | **The market floor rises to what the cohort target actually costs, and the fallback is decided in advance rather than under pressure.** 40 Kalshi cohorts at `n_train >= 30` implies on the order of **7 000 markets**, not the 2 000 of decision D-R7, and `docs/BUILD_STATE.md` section 7.5 puts the reachable in-window Kalshi listing at about 15 000 rows living a week or more. So the target is reachable but consumes about half the universe, and DS1 must report the reachable count against the target before building. If the 365-day window cannot deliver it, the ordered fallback is: first widen `window_days` toward the 730-day ceiling of decision D-S3, then relax the `min_trades` filter with the count stated per filter, and **only last** lower the cohort target, with the reason recorded. Widening the window costs contamination risk for LLM agents alone, which the clean-market rule already handles; lowering the cohort target costs the comparison itself, which nothing else recovers. | Contract 7.4 (C1c); DS1; gate G3 |
| D-S13 | **Cohort work cannot start before the fold fix of decisions D-R1 and D-R2 lands.** All six cohorts that reach ten markets today sit entirely inside one fold, a direct consequence of the inverted 111 / 46 / 130 split, and a cohort confined to one fold can carry neither a paired lower bound nor an out-of-time replication. Package DS2 therefore measures cohorts only on a dataset rebuilt with count-quantile, cluster-aware folds, and the loader reports, per cohort, its per-fold counts and a `usable_for_paired_test` flag that is false when any fold is empty. | DS1 before DS2 inside lot 5b; contract 7.7 and 12.7 (C1c) |
| D-S14 | **The coverage threshold of decision D-S9 becomes per venue, and the vocabulary starts from the measured rules rather than from an invented list.** A single 95 percent bar is unreachable on Manifold by construction. The build reports coverage per venue and per facet; a venue below **90 percent** subject coverage is labelled `taxonomy: "weak"` for that venue only, and Manifold's `other` bucket is expected to be large and is reported rather than hidden. The vocabulary DS2 ships starts from the measured prototype: the structure facet needs at least `threshold-above` (145 Kalshi markets), `threshold-below` (15), `count-over-period` (10), `head-to-head` (9), `range-band` (7) and `by-date` (7 on Kalshi, 12 on Manifold), and the subject facet at least `bitcoin`, `gold-silver`, `gas-prices`, `oil`, `cpi-inflation`, `treasury-yields`, `equity-index`, `single-equity`, `precipitation`, `temperature`, `elections-us`, `us-executive`, `armed-conflict`, `ai-models`, `spaceflight`, `net-worth` and `platform-meta` (the last one being how a self-referential Manifold market is named and excluded from forecast cohorts rather than silently tagged `other`). Measured: **7 of the 67 Manifold markets** are self-referential ("Do you like 4 percent odds?", "Will this market get more than 100 traders?", "We sell more than twice the boosts now that we add 5k liquidity to the AMM?"), while **8** carry the existing `nonpredictive` provider tag, and the two sets are not the same, so DS2 must reconcile them into one audited `platform-meta` subject rather than trusting either alone. | DS2; contract 7.14 (C1c); AC-34 restated |

The restated criteria: **AC-32** asks for 40 usable Kalshi cohorts and 8 Manifold cohorts, with the market
count and the reachable universe reported against the target and the fallback order followed and recorded.
**AC-34** asks for per-venue coverage above 90 percent on the subject facet for Kalshi, the measured
structure vocabulary populated, the `platform-meta` markets excluded from forecast cohorts, and per-cohort
per-fold counts with the `usable_for_paired_test` flag.

## F. What this does not change

The as-of law, the integer law and replay by hash are untouched: a tag is data about a market that exists
before the first bar, so it is available at every decision instant and adds no leak. The separation of
forecast skill from trading result, the sealed fold, the claims ledger and its candidate count, and the
Manifold separation rule of decision D-R12 all stand as written. Nothing here weakens the folds of
decisions D-R1 and D-R2: a cohort is cut inside the folds, never across them, and a cohort whose markets
fall in one fold only is reported and unusable for a paired comparison.
