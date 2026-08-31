## Adversarial completeness review - PRD vs delivered contract

Read: PRD (380 lines, full), `docs/CONTRACTS.md` (1931 lines, full), `types.py`, `events.py`, `rng.py`, `errors.py`, both schemas, `pyproject.toml`, `README.md`, and the (empty) `tests/` tree.

Findings ranked by severity. Every one is a concrete missing assignment (module / signature / test) or a self-contradiction that will make two workstreams build incompatible code.

---

### BLOCKERS - the first match cannot run as specified

**1. `MatchConfig` carries a float, and `canonical_json` refuses floats. The very first event of every journal raises.**
- File: `src/pxe/types.py:1552` — `agent_timeout_s: float = 60.0`
- File: `docs/CONTRACTS.md:322` — "`MatchConfig` is journalled verbatim in `MatchStarted.config`."
- File: `src/pxe/events.py:136-141` — `if isinstance(value, float): raise NonCanonicalValueError(...)`
- Self-contradiction inside one docstring: `types.py:1512` says "Every field is part of the journal (``MatchStarted.config``)" and `types.py:1530-1531` says `agent_timeout_s` "Lives outside the pure engine and is never journalled."
- Why it breaks: `MatchStarted.config` is built from `asdict(MatchConfig)`. `_encode` walks it and raises on `agent_timeout_s`. Every match aborts at `seq == 1`. A09 will discover this on day one and will "fix" it by silently dropping the field, which changes the journal hash after golden fixtures are frozen.
- Fix: move the timeout out of `MatchConfig` into `GatewayConfig` (which §2.6 already declares non-journalled), or make it integral: replace with `agent_timeout_ms: int = 60_000` **and** add to §2.6: "`MatchStarted.config` is `canonical_json`-encodable by construction: `MatchConfig` may not contain a float. `test_types.py::test_match_config_is_canonical_json_encodable` enforces it."

**2. `mm_initial_cash_cents` is required by invariant I2 and by `AccountBook.__init__`, but the field does not exist.**
- File: `docs/CONTRACTS.md:698` — "`sum over all accounts of cash_cents(a) == n_agents * initial_cash_cents + mm_initial_cash_cents`"
- File: `docs/CONTRACTS.md:1042` — `def __init__(self, *, agent_ids, market_ids, initial_cash_cents: int, mm_initial_cash_cents: int, taker_fee_bps: int)`
- File: `docs/CONTRACTS.md:1929` — decision 16 claims it "enters invariant I2 and is journalled".
- File: `src/pxe/types.py:1541-1558` — `MatchConfig` has no such field. `grep -r mm_initial_cash src/` returns nothing.
- Why it breaks: A09 constructs `AccountBook` and has no value to pass. It will invent a constant; A06's I2 will then be checked against a different constant; the invariant fails or is silently weakened. It is also claimed as journalled, so its absence changes the AC-P1 artefact once added.
- Fix: add to `MatchConfig` immediately after `initial_cash_cents`: `mm_initial_cash_cents: int = 10_000_000` with `__post_init__` check `>= initial_cash_cents`, and state in §6.2: "`mm_initial_cash_cents` comes from `MatchConfig` and nowhere else."

**3. The canonical account order is stated three different ways, and the code implements the third.**
- File: `docs/CONTRACTS.md:278-280` — "ranked agents ascending numeric suffix, then `MM`, then `FEES`. This is the *canonical account order*, used by `AccountBook.account_ids()` and by every per account event loop."
- File: `docs/CONTRACTS.md:1035` — `def account_ids(self) -> tuple[str, ...]        # canonical order: agents, MM, FEES`
- File: `src/pxe/events.py:947-949` (`PositionSnapshot` docstring) — "Emitted once per account in ascending ``account_id`` order, agents first then ``FEES`` then ``MM``"
- File: `src/pxe/types.py:1806-1824` — `sorted_ids` falls through to lexicographic for non-`M`/`A` ids, so `sorted_ids(["A1","MM","FEES"]) == ("A1","FEES","MM")`.
- Why it breaks: `PositionSnapshot` and `SettlementApplied` are emitted once per account, so the account order is literally the journal byte order. Two implementations that both "follow the contract" produce different `journal_hash`. This is AC-P1, the top invariant.
- Fix: pick one and delete the other two statements. Recommended: add an explicit helper to `pxe.types` rather than overloading `sorted_ids` — `def sorted_account_ids(ids: Sequence[str]) -> tuple[str, ...]` returning ranked agents ascending, then `MM_ACCOUNT_ID`, then `FEES_ACCOUNT_ID`; state in §2.3 that `sorted_ids` is for markets and agents only and must never be given `MM`/`FEES`; correct the `PositionSnapshot` docstring; add `test_types.py::test_canonical_account_order`.

**4. FR-5.4.5 scenario-scripted market cancellation has no data field, no producer and no signature. P1 step 5 calls something that does not exist.**
- PRD FR-5.4.5: "Un marché ne peut être annulé que par le script du scénario ; l'annulation dénoue toutes les exécutions et restitue le cash."
- File: `docs/CONTRACTS.md:594-595` — "5. Scenario scripted cancellations, if any, follow the same shape with `MarketCancelled` and `mode=\"unwind\"` settlements."
- File: `src/pxe/types.py:1599-1608` — `ScenarioSpec` has `markets`, `correlations`, `talking_mode`, `liquidity_profile_name`, `held_out`, `notes`. No cancellation plan.
- File: `docs/CONTRACTS.md:1128-1133` — `Oracle` exposes `due_market_ids(tick)` and `cancel_market(...)` but nothing tells the runner *when* to cancel.
- Why it breaks: A09 has no callable to ask "which markets are cancelled at tick t"; A03 has no field to write the plan into; `MarketCancelled`, `CancelReason.MARKET_CANCELLED`, `mode="unwind"` and `test_oracle.py::test_cancel_unwinds_everything` are all unreachable. FR-5.4.5 is half-implemented by construction.
- Fix: add to `ScenarioSpec`: `cancellations: tuple[tuple[int, str, str], ...] = ()  # (tick, market_id, reason), sorted by (tick, market_id)`, validated in `__post_init__` against `markets` and `ticks_total`; add to §7.11 `def due_cancellations(self, tick: int) -> tuple[tuple[str, str], ...]  # (market_id, reason), ascending market_id`; name the test `test_oracle.py::test_scripted_cancellation_at_scheduled_tick`.

**5. The bankruptcy predicate is unreachable, so FR-5.5.5 and decisions 9/13 are dead code.**
- File: `docs/CONTRACTS.md:632-633` — "any ranked, non frozen agent with `equity_cents <= config.bankruptcy_equity_floor_cents` is frozen" with `bankruptcy_equity_floor_cents: int = 0` (`types.py:1555`).
- PRD FR-5.5.5: "Faillite (**cash et collatéral libres épuisés**) : ordres annulés, agent gelé jusqu'à la fin."
- Why it breaks: given I4 (`free_cash_cents(a) >= 0`) and I9 (`cash_cents(a) >= 0`), and short collateral of `100 * qty` (decision 3), equity is always `>= free_cash_cents >= 0`. `equity <= 0` requires cash to exactly equal the short worst case with every long worth zero. In practice no agent is ever frozen: `AgentFrozen`, `CancelReason.AGENT_FROZEN`, `RejectReason.AGENT_FROZEN`, `active_agent_ids()`, decisions 9 and 13 and `test_match_runner.py::test_bankruptcy_freezes_agent` all become untestable except by hand-forged state. Meanwhile the PRD's actual trigger (free cash exhausted) fires often and is not implemented at all.
- Fix: replace step 14's predicate with the PRD's: "freeze any ranked, non frozen agent whose `free_cash_cents(a) <= config.bankruptcy_free_cash_floor_cents` **and** whose `equity_cents < config.bankruptcy_equity_floor_cents`", or more simply state the PRD condition literally: `free_cash_cents(a) == 0 and accounts.resting_order_count(a) == 0 and every position is flat or fully collateral-locked`. Rename the config field to `bankruptcy_free_cash_floor_cents: int = 0` and add `bankruptcy_equity_floor_cents` only if you keep a second gate. Add `test_accounts.py::test_freeze_triggers_when_free_cash_exhausted` with a constructed flow that actually reaches it.

**6. `AccountBook.check_invariants` cannot evaluate I5, I6, I8 or I10 from its own signature.**
- File: `docs/CONTRACTS.md:1063-1065` — `def check_invariants(self, *, book_view: Mapping[str, Sequence[Order]] | None = None, ref_prices: Mapping[str, int] | None = None) -> None` with `"""Raises InvariantViolationError naming the first breach among I1..I11."""`
- File: `docs/CONTRACTS.md:1042` — `AccountBook.__init__` receives only `agent_ids, market_ids, initial_cash_cents, mm_initial_cash_cents, taker_fee_bps`.
- Why it breaks: I8 needs `max_active_orders_per_market` (not passed, not stored). I10 needs `mm.inventory_max` (not passed, not stored). I5 is per-trade and I6 is per-settlement-group, and `AccountBook` keeps no trade or settlement history. So four of the eleven invariants that P4 step 15 claims to run every tick simply cannot run. A06 will quietly skip them and `test_invariants.py` will pass vacuously, which §10's own anti-vacuous-pass rule forbids.
- Fix: either widen the constructor — `def __init__(self, *, agent_ids, market_ids, config: MatchConfig) -> None` (it already needs `initial_cash_cents`, `mm_initial_cash_cents`, `taker_fee_bps`, `max_active_orders_per_market` and `mm.inventory_max`, all of which live on `MatchConfig`) — or split the invariants explicitly: `check_state_invariants(*, book_view, ref_prices)` for I1..I4, I7..I11, and `check_trade_invariant(trade, deltas)` / `check_settlement_invariant(lines)` called at the point of the event for I5/I6. Also reconcile `docs/CONTRACTS.md:634` and `:691`, which both call it positionally (`check_invariants(ref_prices)`) against a keyword-only signature.

**7. `MatchEnded` / `MatchResult` require `brier_ppm` and `incident_count`, which the runner cannot produce without breaking the dependency direction.**
- File: `docs/CONTRACTS.md:519` — `match_ended ... rankings[]`; `src/pxe/events.py:391-393` — rankings hold "``rank``, ``agent_id``, ``pnl_cents``, ``final_cash_cents``, ``pnl_pct_bps``, ``brier_ppm``".
- File: `src/pxe/types.py:1765-1774` — `MatchResult.incident_count: int`.
- File: `docs/CONTRACTS.md:730-736` — dependency arrows put `metrics` and `integrity` strictly downstream of `runner`; `docs/CONTRACTS.md:525-528` — detectors "run offline over a finished journal".
- Why it breaks: `MatchRunner.run() -> MatchResult` must fill `brier_ppm` (owned by A16, `metrics/calibration.py`) and `incident_count` (owned by A18, offline). Either A09 imports downstream modules (violating §7's arrows and FR-5.1.2 purity discipline), or A09 reimplements the Brier (two definitions of the headline calibration metric, which is exactly what AC-P4 forbids), or both fields are always zero and `test_metrics_performance.py::test_ranking_is_settled_not_marked` compares against garbage.
- Fix: drop `brier_ppm` from `MatchRanking` and from `MatchEnded.rankings`; keep ranking in the runner as PnL-only (`rank`, `agent_id`, `pnl_cents`, `final_cash_cents`, `pnl_pct_bps`) per FR-5.5.4, and let `metrics.calibration` attach Brier in the projection. Replace `MatchResult.incident_count: int` with nothing, and state that incident counts belong to `incidents.jsonl` and the report only. Add a `RankedResult` type in `metrics` if the report wants the joined view.

---

### HIGH - a PRD deliverable has no owner, no signature or no test

**8. `tests/` is empty and CI does not exist, yet T1.1 is the exit gate of M0 and A01 owns five test files.**
- File: `docs/CONTRACTS.md:139-143` — table 1 assigns `tests/conftest.py`, `tests/test_types.py`, `tests/test_events.py`, `tests/test_rng.py`, `tests/test_schemas.py` to A01.
- File: `docs/CONTRACTS.md:1843` — "| T1.1 monorepo, CI, quality | A01 | `pytest`, `ruff`, `mypy` green, coverage published |"
- Reality: `ls tests` → empty. No `Makefile`, no `.github/`, and table 1 contains **no entry for a CI workflow file or a Makefile**, so T1.1's actual deliverable ("`make test` vert en CI ; lint + typage ; couverture publiée") is owned by nobody and lives in no file.
- Why it breaks: `types`, `events`, `rng`, `errors` are marked "(A01, done)" in §7.1-7.3 with zero committed tests. §10's fixtures (`tmp_journal`, `standard_config`, `tiny_world`, `flat_accounts`, `scripted_gateway`) are declared "Nobody else defines a fixture with those names" but do not exist, so every one of the other 24 workstreams is blocked or will define its own.
- Fix: add to table 1: `Makefile  A01`, `.github/workflows/ci.yml  A01`. Deliver `tests/conftest.py` with the five named fixtures and the five A01 test modules before any other workstream starts, and change the §7.1-7.3 headings from "(A01, done)" to "(A01, done: <test file>)".

**9. `tournament/report.py` has no public API at all, but three product ACs depend on it.**
- File: `docs/CONTRACTS.md:128` — `tournament/report.py   A23` in table 1.
- Referenced as the owning module at `:1830` (AC-P3), `:1832` (AC-P5), `:1861` (T3.6), `:1869` (T5.6). §7.19 documents `latin_square`, `orchestrator`, `ratings`, `elites`, `halloffame`, `heldout` — and stops. §7.22 documents only `cli.main`.
- PRD T3.6: "Fin de tournoi → rapport MD/HTML auto (classement, deltas, coûts, incidents, coût de la liquidité) sans action manuelle." PRD T3.5: "rapports séparés train / held-out." PRD T5.6: "Brier + courbes de fiabilité par modèle dans les rapports ; analyse Brier vs PnL publiée."
- Why it breaks: A23 has a CLI verb (`pxe report build`) and no function to call. The five mandated report sections, the train/held-out split and the reliability curves have no signature, so `test_report.py::test_reliability_curves` (named at `:1869`) tests nothing that exists.
- Fix: add §7.24 `pxe.tournament.report`:
  ```python
  @dataclass(frozen=True)
  class ReportSections:
      leaderboard: tuple[RatingRecord, ...]
      deltas: tuple[tuple[str, float, float], ...]        # harness_key, mu_delta, ci_width
      costs_usd: tuple[tuple[str, float], ...]
      incidents: tuple[Incident, ...]
      liquidity_cost_cents: tuple[tuple[str, int], ...]   # per liquidity profile
      calibration: tuple[tuple[str, int, tuple[tuple[int, int, int], ...]], ...]

  def build_sections(*, result: TournamentResult, store: Store, held_out: bool) -> ReportSections
  def render_markdown(sections: ReportSections, *, title: str) -> str
  def render_html(sections: ReportSections, *, title: str) -> str
  def write_report(*, result: TournamentResult, store: Store, out_dir: Path) -> tuple[Path, Path]
      """Writes report.md and report.html for the train set and the held-out set separately."""
  ```

**10. `tournament/scheduling.py` has no public API, so two of the three PRD tournament formats have no pairing algorithm.**
- File: `docs/CONTRACTS.md:123` — `tournament/scheduling.py  A19` in table 1; no section 7 entry.
- PRD §8: "Formats : round-robin (petites populations), système suisse (grandes populations), matchs d'exhibition." PRD T3.1 AC: "Round-robin et suisse".
- `TournamentFormat` enum exists (`types.py:350-357`) and `TournamentOrchestrator.plan()` exists, but Swiss pairing needs standings-dependent round-by-round pairing that `plan()` (a single up-front call returning `tuple[MatchTask, ...]`) structurally cannot express.
- Why it breaks: A19 must invent the Swiss algorithm and the round boundary. `plan()`'s return type makes Swiss impossible without redesign after the fact.
- Fix: add §7.19 entries:
  ```python
  # scheduling.py
  def round_robin_pairings(*, harness_keys: Sequence[str], agents_per_match: int) -> tuple[tuple[str, ...], ...]
  def swiss_pairings(*, standings: Sequence[RatingRecord], agents_per_match: int,
                     played: Sequence[frozenset[str]], rng: random.Random) -> tuple[tuple[str, ...], ...]
  def exhibition_pairings(*, harness_keys: Sequence[str], challengers: Sequence[str]) -> tuple[tuple[str, ...], ...]
  ```
  and change the orchestrator to `def plan_round(self, round_index: int, standings: Sequence[RatingRecord]) -> tuple[MatchTask, ...]`, keeping `plan()` as the round-robin/exhibition shortcut. Name the tests `test_tournament.py::test_swiss_pairs_by_standing_without_rematch` and `::test_round_robin_covers_every_matchup`.

**11. `MatchProjection` uses five record types that are never defined anywhere.**
- File: `docs/CONTRACTS.md:1388-1392` — `trades: tuple[TradeRecord, ...]`, `orders: tuple[OrderRecord, ...]`, `predictions: tuple[PredictionRecord, ...]`, `signals: tuple[SignalRecord, ...]`, `messages: tuple[MessageRecord, ...]`.
- `grep -n "TradeRecord" docs/CONTRACTS.md` → one hit, the usage. Same for the other four.
- Why it breaks: `MatchProjection` is declared "The one and only journal reader for metrics. Every metric module consumes a MatchProjection". A15 owns `projection.py`; A16, A17, A18 and A22 all read those five tuples and cannot know their fields. `maker_ratio_ppm` needs `TradeRecord.maker_agent_id`; `reaction_latency_milli` needs `SignalRecord.tick`/`market_id`; the spoofing detector needs `OrderRecord.cancelled_tick`. Every consumer will guess a different shape.
- Fix: define all five frozen dataclasses in §7.17 with explicit fields before A15 starts, minimally:
  ```python
  @dataclass(frozen=True)
  class TradeRecord: trade_id: str; tick: int; market_id: str; price: int; qty: int; maker_agent_id: str; maker_side: str; taker_agent_id: str; taker_side: str; taker_fee_cents: int
  @dataclass(frozen=True)
  class OrderRecord: order_id: str; agent_id: str; market_id: str; side: str; requested_type: str; price: int; qty: int; placed_tick: int; filled_qty: int; cancelled_tick: int | None; cancel_reason: str | None
  @dataclass(frozen=True)
  class PredictionRecord: agent_id: str; market_id: str; tick: int; p_yes_ppm: int; carried: bool
  @dataclass(frozen=True)
  class SignalRecord: signal_id: str; tick: int; agent_id: str; market_id: str; kind: str; value_milli: int; precision_ppm: int
  @dataclass(frozen=True)
  class MessageRecord: agent_id: str; tick: int; text: str; deliver_tick: int
  ```

**12. FR-6.2.3's token budget does not exist. Only a USD budget does.**
- PRD FR-6.2.3: "Le harness a droit à un **budget de tokens** et un timeout par tick, configurés par tournoi."
- File: `src/pxe/types.py:1691-1697` — `GatewayConfig` has `timeout_s`, `retries`, `max_budget_usd_per_call/_match/_tournament`, `max_parallel_calls`, `trace_dir`. No token cap.
- File: `docs/CONTRACTS.md:1316-1322` — `BudgetTracker.check(*, scope: str, amount_usd: float)`, `spent_usd`, `remaining_usd`. USD only.
- File: `docs/CONTRACTS.md:1822` maps FR-6.2.3 to `test_budget.py::test_budget_cap_enforced`, which by that signature can only assert the dollar cap.
- Why it breaks: half of FR-6.2.3 has no field, no signature, no test. It is also the only lever that bounds an agent's *output* length independently of price, which matters for T2.4's 2000-token observation budget being meaningful.
- Fix: add `max_output_tokens_per_call: int = 2048` and `max_input_tokens_per_call: int = 8192` to `GatewayConfig`; add `def check_tokens(self, *, input_tokens: int, output_tokens: int) -> None` and `def spent_tokens(self, scope: str = "match") -> tuple[int, int]` to `BudgetTracker`; pass `--max-tokens` (or the harness equivalent) in `build_cli_argv`; name the test `test_budget.py::test_token_cap_enforced`.

**13. PRD section 9 (visualisation and replay) has essentially no contract, and T4.2-T4.5 are collapsed into a single WBS row.**
- File: `docs/CONTRACTS.md:188` — `ui/    A24  (React + Vite, no Python)`. That is the entire UI contract.
- File: `docs/CONTRACTS.md:1866` — "| T4.2 to T4.5 UI | A24 | `ui/` tests plus the manual AC-P7 protocol |" — four WBS tasks, four distinct acceptance criteria, one row, no named test.
- Unassigned PRD requirements: T4.4 "recherche texte" (no `q` parameter on any endpoint in the §7.21 table); PRD §9 "événements marquants annotés (gros trade, résolution anticipée, alerte d'intégrité)" (no highlights projection, no field on `MatchProjection`); PRD §9 vue tournoi "alertes d'intégrité" and "courbes de progression par version" (`/api/tournaments/{id}` returns only "leaderboard, elites grid, costs"); T4.2 "8 agents distinguables ; lisible sur écran 13\""; T4.1 "< 100 ms par requête sur le match de référence" (no named perf test).
- Why it breaks: A24 receives no data contract, and A22 does not know it must serve search, highlights or per-version progression. AC-P7 (an M3 exit gate) rests on all of it.
- Fix: split `:1866` into four rows with named gates. Add to the §7.21 table: `GET /api/matches/{match_id}/decisions?agent_id&from_tick&to_tick&q` (the decision journal with text search over headline/rationale/message), `GET /api/matches/{match_id}/highlights` (served from a new `MatchProjection.highlights: tuple[Highlight, ...]` with `Highlight(tick, kind, agent_ids, market_id, magnitude_cents)` produced by A15), and extend `/api/tournaments/{tournament_id}` to "leaderboard, elites grid, costs, **incidents, per-version mu/sigma series**". Add `test_api.py::test_reference_match_tick_under_100ms` (marked `slow`).

**14. Persistence: `Store` has a writer for four entities out of the twenty-one it claims to mirror, and nothing writes `metrics.json`.**
- File: `docs/CONTRACTS.md:1605-1607` — "Tables mirror PRD section 10.4 exactly: `scenario_template`, `scenario_instance`, `match`, `agent`, `harness_version`, `tick`, `news_item`, `signal`, `order`, `trade`, `position_snapshot`, `prediction`, `resolution`, `settlement`, `metric_record`, `rating_record`, `elite_cell`, `incident`, `tournament`, `heldout_registry`, `mm_config`."
- File: `docs/CONTRACTS.md:1590-1600` — the `Store` API is `save_match`, `has_match`, `load_journal`, `list_matches`, `save_ratings`, `save_incidents`, `save_task`, `pending_tasks`. Nothing writes `elite_cell` (T5.2), `heldout_registry` (T3.5), `metric_record` (T5.6, `/api/matches/{id}/metrics`), `tournament`, `harness_version` (T3.4).
- File: `docs/CONTRACTS.md:539` — `metrics.json  projected metrics  (A15/A16/A17)`, but §7.17 has no writer and no aggregator: nothing turns `tuple[PerformanceMetrics]` + `tuple[CalibrationMetrics]` + `tuple[BehavioralDescriptors]` into a file or a store row. `Store.save_match(result, projection)` takes no metrics argument.
- Why it breaks: `/api/matches/{match_id}/metrics` is contractually forbidden from recomputing ("The API never recomputes engine logic") and has no artefact to read. T5.2's archive and T3.5's sealed bank have tables and no writers.
- Fix: add to §7.17 `@dataclass(frozen=True) class MatchMetrics: performance; calibration; descriptors; mm_pnl_cents; fees_collected_cents`, `def compute_all(projection: MatchProjection) -> MatchMetrics`, `def write_metrics(path: Path, metrics: MatchMetrics) -> None`, `def read_metrics(path: Path) -> MatchMetrics`. Change `Store.save_match(self, result: MatchResult, projection: MatchProjection, metrics: MatchMetrics) -> None` and add `save_elites(tournament_id, cells)`, `save_heldout_access(entries)`, `save_harness_version(harness)`, `save_tournament(config)`. Also add `def write_observation(path: Path, obs: Observation) -> None` to §7.13 - `observations.jsonl` is assigned to A10 at `:536` with no writer signature.

---

### MEDIUM - real ambiguity that will produce divergent implementations

**15. Brier off-by-one at the resolution tick: the engine cannot emit the term the metric definition requires.**
- PRD §7.2: "un marché cesse de compter **après** son tick de résolution". File `docs/CONTRACTS.md:1725` restates it: "A market stops counting strictly after its resolution tick."
- File: `docs/CONTRACTS.md:576-586` — P1 step 4 resolves due markets and marks them `RESOLVED` *before* step 6 builds observations; `docs/CONTRACTS.md:598-599` — P2 emits `PredictionRecorded` "for each **open** market".
- Why it breaks: at tick `r` the market is already `RESOLVED` when predictions are recorded, so `PredictionRecorded` exists only for ticks `1..r-1`. A16 computing the denominator as `r` divides by a tick with no term; computing it as `r-1` contradicts the stated definition. Either way the Brier of an agent differs by module.
- Fix: state it unambiguously in §9: "Terms exist for ticks `1..resolution_tick - 1` of each market, because the market is resolved in P1 before P2 collects predictions. `n_terms` is `sum over markets of (resolution_tick - 1)` for an agent that played every tick." Add `test_metrics_calibration.py::test_n_terms_excludes_the_resolution_tick`.

**16. `observation.v1.json` requires at least one open market, which FR-5.2.3 makes false.**
- File: `schemas/observation.v1.json` — `"markets": { "type": "array", "minItems": 1, "maxItems": 8, ... }`
- PRD FR-5.2.3 and §5.7: "Tick de résolution par marché | T (final) | **1–T**".
- Why it breaks: any scenario where all markets resolve before `T` produces a tick with zero open markets. `validate_observation` then raises `ObservationValidationError` in P1, aborting a legal match. This also collides with §5's P1 step 6, which builds an observation for every non-frozen agent unconditionally.
- Fix: `"minItems": 0`. Add `test_observation_builder.py::test_observation_valid_when_all_markets_resolved`, and state in §5 P1 step 6 whether the runner still calls the gateway when no market is open (recommendation: skip the gateway call, emit `ObservationBuilt` with `n_markets: 0`, record no predictions).

**17. The journalled `obs_hash` is derived from floats through a banned `round()`, contradicting decision 2 and §3.5.**
- File: `docs/CONTRACTS.md:426` — forbidden in a journal: "floats (structurally rejected by `canonical_json`)"; decision 2 at `:1884` claims this makes AC-P1 "structurally safe rather than dependent on float repr".
- File: `src/pxe/events.py:186` — `_encode_stable` does `return round(value, 6)`, and `payload_hash` = `blake2b(stable_json(...))`.
- File: `docs/CONTRACTS.md:235-236` — "`round()` is banker's rounding and is banned. Use `pxe.types.round_half_up`."
- Why it breaks: `ObservationBuilt.obs_hash` **is** journalled (`:511`), so the AC-P1 hash chain depends on float rounding and `json.dumps` float repr after all, and it uses the exact function the contract bans. The claim in decision 2 is false as written.
- Fix: either build the observation payload from `*_ppm` integers only (drop floats from the observation and let the prompt builder convert), or amend §3.5 and decision 2 to say explicitly: "one float-derived value enters the journal, `obs_hash`; it is stable because `stable_json` rounds to 6 decimals with `round_half_up` on the scaled integer and CPython emits shortest-repr floats". If you keep floats, replace `round(value, 6)` with an integer-scaled `round_half_up(value * 1_000_000) / 1_000_000` so the banned function disappears.

**18. Markets per world (PRD default 5, range 2-8) is not a parameter anywhere.**
- PRD §5.7: "| Marchés par monde | 5 | 2–8 |"; FR-5.2.1: "De 2 à 8 marchés par monde".
- File: `docs/CONTRACTS.md:906-915` — `def generate_world(*, template_id, seed, ticks_total=48, liquidity=..., talking_mode=False, held_out=False) -> World`. No market count. `MatchConfig` has none either. Only `ScenarioSpec.__post_init__` (`types.py:1611`) validates `2 <= len(markets) <= 8` after the fact.
- Why it breaks: the market count becomes a hard-coded template constant, so the PRD's tunable difficulty axis and FR-5.2.1's stated range are untestable. `test_world_gen.py::test_market_count_and_correlations` has no knob to sweep.
- Fix: add `n_markets: int = 5` to `generate_world` and to `WorldTemplate.build(self, *, seed, ticks_total, n_markets, rng)`, validated `2 <= n_markets <= 8`; add `n_markets: int = 5` to `MatchConfig` so it is journalled and the runner can assert `len(scenario.markets) == config.n_markets`.

**19. FR-5.3.2 Latin square: 3 profile kinds, 4-8 seats, 3 seeds by default - exact balance is arithmetically impossible and no rule says what to do.**
- PRD FR-5.3.2: "chaque harness occupe chaque profil **un nombre égal de fois**"; PRD §5.7: "| Seeds par matchup | 3 | ≥ 3 |".
- File: `docs/CONTRACTS.md:1486-1490` — `latin_square(n)`, `assign_profiles(*, agent_ids, profile_kinds, seed_index)`, `verify_balance(assignments) -> bool`. `InfoProfileKind` has exactly 3 members (`types.py:262-268`).
- Why it breaks: with 6 seats and 3 kinds, a square of order 6 needs 6 symbols; with 3 seeds and 6 seats, each harness sees 3 of 3 kinds only if kinds repeat two-per-square in a specified pattern. Nothing states how 3 kinds map onto `n` seats, nor that the seed count must be a multiple of the number of distinct kinds. `verify_balance` will return `False` for the PRD's own defaults and AC-P3 ("3 seeds/matchup avec carré latin") fails.
- Fix: state the rule in §7.19: "`profile_kinds` is expanded to length `len(agent_ids)` by cycling the three kinds in `InfoProfileKind` declaration order; `assign_profiles` rotates that vector by `seed_index % len(agent_ids)`; exact balance (`verify_balance`) holds iff the number of seeds is a multiple of `len(agent_ids)`. `TournamentConfig.__post_init__` raises `InvalidConfigError` when `len(seeds) < 3`, and the report flags 'approximate balance' when `len(seeds) % agents_per_match != 0`." Add `test_latin_square.py::test_balance_requires_seed_multiple`.

**20. `talking_mode` and the liquidity profile each have two owners with no precedence rule, and both are journalled.**
- File: `src/pxe/types.py:1549` and `:1605` — `MatchConfig.talking_mode` and `ScenarioSpec.talking_mode`.
- File: `src/pxe/types.py:1553-1554` and `:1606` — `MatchConfig.mm` + `MatchConfig.liquidity_profile_name` vs `ScenarioSpec.liquidity_profile_name`.
- File: `docs/CONTRACTS.md:906-913` — `generate_world(..., liquidity=..., talking_mode=...)` writes them into the scenario; `MatchRunner.__init__(*, config, world, ...)` receives both objects.
- Why it breaks: the runner reads one, the observation builder may read the other, the market maker is built from `config.mm`; `MatchStarted` journals both. A mismatch is undetectable and changes behaviour (whether messages are delivered, what spread the MM quotes) with no error.
- Fix: pick a single owner. Recommended: the scenario owns neither — delete `talking_mode` and `liquidity_profile_name` from `ScenarioSpec` and keep `MatchConfig` as the sole source, or keep them on `ScenarioSpec` and make `MatchRunner.__init__` raise `InvalidConfigError` when `config.talking_mode != world.scenario.talking_mode` or `config.liquidity_profile_name != world.scenario.liquidity_profile_name`. State whichever you choose in §2.6 and add `test_match_runner.py::test_config_and_scenario_agree`.

**21. Nothing computes `HarnessConfig.config_hash`, which T3.4 requires.**
- File: `src/pxe/types.py:1669` — `config_hash: str = ""` (a plain field, default empty).
- PRD T3.4: "Versions gelées (**hash config+prompt**) rejouables à l'identique".
- File: `docs/CONTRACTS.md:1568` — `HallOfFame.freeze(harness, rating) -> str  # returns harness_key`, and §2.2 says the harness key is `<harness_id>@<version>`, "Assigned by gateway". `grep -n config_hash docs/CONTRACTS.md` → zero hits.
- Why it breaks: `MatchStarted.agents` journals `config_hash` (`events.py:347-349`), so a default of `""` puts an empty hash into every journal and makes frozen-version identity unverifiable. A20's `test_elites.py::test_frozen_harness_replays_identically` has nothing to compare.
- Fix: add to §7.1 and `pxe.types`: `def harness_config_hash(harness: HarnessConfig) -> str  # blake2b-256 over canonical_json of (harness_id, version, kind, model, system_prompt, params), 16 hex chars`, and `def harness_key(harness: HarnessConfig) -> str  # f"{harness_id}@{version}+{config_hash[:8]}"`. Make `HarnessConfig.__post_init__` fill `config_hash` when empty. Add `test_types.py::test_harness_hash_is_stable_across_processes`.

**22. T2.6's own acceptance criteria are only half assigned.**
- PRD T2.6: "Cotation bilatérale ≥ 95 % des ticks ; **spread moyen conforme au profil ± 1 ¢** ; |inventaire| ≤ I_max ; élargissement post-news vérifié ; 3 presets recettés ; **perte moyenne du MM mesurée et documentée sur 200 matchs de baselines**."
- File: `docs/CONTRACTS.md:1864` — "| T2.6 reference market maker (blocks M1) | A07 | `test_market_maker.py` (all of FR-5.8.x) |" - one file, no named test for the ±1 c spread conformity and none at all for the 200-match loss measurement, which is a *documented artefact*, not an assertion.
- Same pattern elsewhere: T3.2's "σ décroissant" and "ordre attendu des baselines retrouvé sur 200 matchs" → only `test_ratings.py`; T2.2's "fondamentaliste > noise trader en TrueSkill (significatif)" → only `test_baselines.py`; T5.1's "stabilité inter-seeds (corrélation > 0,6)" → only `test_metrics_behavioral.py`; T2.5's "appels des agents parallélisés" and "le timeout d'un agent n'allonge pas le tick au-delà du seuil" → only `test_budget.py`.
- Fix: name each one. `test_market_maker.py::test_mean_spread_within_one_cent_of_profile` (`statistical`), `test_market_maker.py::test_two_sided_on_95pct_of_ticks`, plus a CLI verb `pxe mm study --profile <p> --matches 200` writing `docs/MM_LIQUIDITY_COST.md` (add that document to table 1, owner A07). `test_ratings.py::test_sigma_decreases` and `::test_baseline_order_recovered` (`slow`, `statistical`). `test_baselines.py::test_fundamentalist_beats_noise_trader` (`slow`, `statistical`). `test_metrics_behavioral.py::test_descriptors_stable_across_seeds` (`statistical`). `test_budget.py::test_calls_run_in_parallel` and `::test_slow_agent_does_not_extend_tick_beyond_timeout`.

---

### LOW - narrow but concrete

**23. Private signals may reference already-resolved markets and nothing forbids it.**
- File: `docs/CONTRACTS.md:938-939` — `def signals_for_tick(self, tick: int) -> tuple[Signal, ...]` with no market-status argument; `InfoEngine.__init__` receives `world` and `ticks_total` but is never told which markets have resolved. `InfoProfile.delay_ticks` (`types.py:1146`) makes a delayed signal about a market that resolved in the meantime routine.
- `schemas/observation.v1.json` `signals.items.market_id` is a bare `marketId` with no constraint that it appears in `markets`.
- Why it breaks: an agent receives a signal about a market it can no longer trade or predict; `reaction_latency_milli` (which measures signal → next trade on that market) is then undefined for those signals; the LLM prompt contains a market_id absent from `markets`.
- Fix: state in §5 P1 step 3: "signals whose `market_id` is not in `state.open_market_ids()` at this tick are dropped before emission, not journalled." Add `test_info_engine.py::test_no_signal_for_a_resolved_market`.

**24. §12 records three functional deviations from the PRD as "decisions", while the document's own rule 1 says the PRD wins.**
- File: `docs/CONTRACTS.md:8-10` — "If this document and the PRD disagree on a functional point, **the PRD wins** and this document must be amended in the same commit."
- Deviating decisions: 1 (`initial_cash_cents = 1_000_000`, a 100x reading of PRD §5.7), 3 (short position collateral `100 x qty` vs FR-5.5.1's literal `(100 - p) x qty`), 9 (frozen agents produce no Brier terms vs PRD §7.2's "moyenne uniforme sur {ticks où le marché est ouvert} x {marchés}").
- Why it breaks: decisions 1 and 3 are defensible (3 is in fact arithmetically equivalent to FR-5.5.1 on free cash, and I verified it: the free-cash delta at execution is exactly zero on both sides). But as long as they live only in §12, an implementer reading the PRD - which rule 1 tells them to prefer - builds a different system. Decision 9 additionally makes `MatchRanking.brier_ppm` non-comparable across agents with different `n_terms`.
- Fix: amend the PRD in the same commit, as rule 1 requires: §5.7 "Cash initial | 10 000 contrats (1 000 000 ¢)"; FR-5.5.1 gains a sentence distinguishing order escrow from position escrow; §7.2 gains "un agent gelé cesse de produire des termes ; le rapport publie `n_terms`". Then reduce §12 entries 1, 3 and 9 to pointers at the amended PRD text.

**25. Minor schema and signature nits.**
- `schemas/observation.v1.json` `$defs.agentId` is `^(A[1-9][0-9]?|MM)$` while `src/pxe/types.py:153` `RE_AGENT_ID` is `^(A[1-9][0-9]?|MM|FEES)$` - harmless today because `FEES` never appears in an observation, but the two regexes are stated as the same concept in §2.2. Split them: `RE_ACCOUNT_ID` (agents + MM + FEES) and `RE_AGENT_ID` (agents only).
- `docs/CONTRACTS.md:634` and `:691` call `accounts.check_invariants(ref_prices)` positionally against the keyword-only signature at `:1063`. §7's preamble says "argument names are part of the contract"; fix the two call sites to `check_invariants(book_view=..., ref_prices=...)`.
- `schemas/action.v1.json` hard-codes `"orders": {"maxItems": 20}` and `"predictions": {"maxItems": 8}` while `MatchConfig.max_orders_per_action` is a configurable field (`types.py:1551`, validated only `>= 1`). Either cap `max_orders_per_action` at 20 in `__post_init__` or state in §8.2 that the schema encodes the maximum permitted config value.
- PRD §15 KPIs (matchs/nuit, "taux de matchs terminés sans incident technique >= 99 %", "sigma TrueSkill median apres 20 matchs <= 1/3 du sigma initial", cout moyen par match, engagement replay) are assigned to no module, no signature and no report section. At minimum add them to the `ReportSections` of finding 9 as a `kpis: tuple[tuple[str, int], ...]` field.
