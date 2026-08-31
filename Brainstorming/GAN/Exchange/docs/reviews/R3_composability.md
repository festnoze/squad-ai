I read the PRD in full, then every delivered file, and verified several findings by executing the code. Findings ranked by severity.

---

## BLOCKERS (two agents will produce code that cannot run together)

**1. `MatchConfig` cannot be journalled at all: `MatchStarted` crashes on the first event of every match.**
`src/pxe/types.py:1552` — `agent_timeout_s: float = 60.0`, inside a dataclass whose docstring says *"Every field is part of the journal (`MatchStarted.config`)"*. `docs/CONTRACTS.md:4.5` requires `match_started` to carry `config`. Verified:

```
canonical_json(dataclasses.asdict(MatchConfig(seed=1)))
-> NonCanonicalValueError [NON_CANONICAL_VALUE] floats are forbidden in the journal
   (path='$.agent_timeout_s', value='60.0')
```

It is also a wall-clock value, explicitly banned by §2.6 (*"`GatewayConfig` is **not** journalled: it is wall clock and cost dependent"*) and §3.5. A09 emits it, A02 hashes it, and both die on tick 0. **Fix:** delete `agent_timeout_s` from `MatchConfig` (it duplicates `GatewayConfig.timeout_s`, which already owns the timeout), and add to §7.1 the two functions that A02/A09/A22 all need and nobody currently owns:
```python
def config_to_journal_dict(config: MatchConfig) -> dict[str, Any]   # ints/str/bool only
def config_from_journal_dict(data: Mapping[str, Any]) -> MatchConfig
```

**2. `mm_initial_cash_cents` is required by three contracts and defined nowhere.**
`CONTRACTS.md:1042` — `def __init__(self, *, agent_ids, market_ids, initial_cash_cents: int, mm_initial_cash_cents: int, taker_fee_bps: int)`; `CONTRACTS.md:709` — *"`I2` uses `mm_initial_cash_cents`, which is a config value (default: 10x an agent's cash) ... and is part of `MatchStarted.config`"*; decision 16 repeats it. `MatchConfig` in `types.py` has no such field (grep confirms zero hits in `src/`). A06 cannot construct an `AccountBook`, A09 cannot supply the argument, and `MatchEnded.mm_pnl_cents` has no baseline to subtract. **Fix:** add to `MatchConfig`, after `initial_cash_cents`:
```python
mm_initial_cash_cents: int = 10_000_000   # 10x initial_cash_cents, FR-5.8.5 / I2
```
and validate `mm_initial_cash_cents >= initial_cash_cents` in `__post_init__`.

**3. The canonical account order is specified three incompatible ways. This alone breaks AC-P1 between workstreams.**
- `CONTRACTS.md:278` — *"ranked agents ascending numeric suffix, then `MM`, then `FEES`"*
- `src/pxe/events.py:943` — *"Emitted once per account in ascending ``account_id`` order, agents first then ``FEES`` then ``MM``"*
- the only shipped helper disagrees with §2.3. Verified: `sorted_ids(['A2','MM','A1','FEES']) == ('A1','A2','FEES','MM')`.

A06 implementing `account_ids()` from §2.3 emits `PositionSnapshot` in a different order than A09 or A15 using `sorted_ids` or the event docstring. Same journal, different bytes, different hash, on two machines. **Fix:** pick §2.3, correct `events.py:943-945` to *"agents ascending, then `MM`, then `FEES`"*, and add the helper that makes it unavoidable:
```python
def sorted_account_ids(ids: Sequence[str]) -> tuple[str, ...]   # agents asc, then MM, then FEES
```
Forbid `sorted_ids` on account ids in §2.3 in one sentence, because it silently produces the wrong answer.

**4. The gateway/validator/runner boundary is self-contradictory: `collect_actions` returns the wrong type and destroys the information P2 needs.**
`CONTRACTS.md:1285` — `def collect_actions(self, *, tick, observations, config) -> tuple[AgentAction, ...]`.
But `CONTRACTS.md:591` (P2 step 8) says the runner then does `validate_action(...)` and emits `AgentActionRejected` per item, and `CONTRACTS.md:1219` types it `validate_action(raw: Any, *, agent_id, tick, config, open_market_ids, resting_order_ids, source)`. Three consequences:
- If the gateway returns `AgentAction`, validation already happened inside the gateway (A13, impure, without `open_market_ids` or `resting_order_ids`, which `collect_actions` never receives) and the `Rejection` list is thrown away, so FR-6.2.2 is unimplementable.
- P2 step 8a — *"if the agent failed: `emit(AgentTimedOut, reason=...)`"* — the reason lives in `AgentReply.error`; `AgentAction` has no error field. A09 literally cannot fill that payload.
- A12 agents return `AgentAction` objects while A14 returns a JSON dict, and both land in `validate_action(raw: Any)` with no rule about which shapes it must accept.

**Fix:** change the protocol to return replies and keep validation in A11/A09:
```python
def collect_actions(self, *, tick: int, observations: Sequence[Observation],
                    config: MatchConfig) -> tuple[AgentReply, ...]:   # sorted by agent_id
async def acollect_actions(...) -> tuple[AgentReply, ...]
```
and state in §7.16: *"`AgentReply.raw` is always a JSON compatible `Mapping` matching `schemas/action.v1.json`, never an `AgentAction`."* Then add the missing serialiser (see finding 12).

**5. Every default match dies at tick `T`: the observation schema forbids the state the runner produces.**
`schemas/observation.v1.json` — `"markets": { "type": "array", "minItems": 1, ... }` and inside `marketBlock`, `"status": { "const": "open" }`. `CONTRACTS.md:563` P1 resolves due markets (step 4) **before** building observations (step 6). PRD 5.7 defaults every market's resolution tick to `T`. So at tick `T` there are zero open markets, `observation_to_json` produces `"markets": []`, and `validate_observation` raises `ObservationValidationError` — which §2.4 classifies as an engine bug that aborts the match.
Second head of the same bug: PRD §7.2 and `CONTRACTS.md:1723` say *"A market stops counting strictly after its resolution tick"*, but P2 only emits `PredictionRecorded` *"for each **open** market"*, so the resolution-tick term (the most informative Brier term) is never recorded. A11 (`resolve_predictions(..., open_market_ids)`) and A16 (calibration expecting `n_terms == resolution_tick`) will disagree on every match.
**Fix:** set `"minItems": 0` in the schema, and in §5 P1 make the resolution sub-step run **after** the observation build for markets whose `resolution_tick == tick` — or, simpler and hash-stable, define explicitly in §8.1 and §9: *"a market with `resolution_tick == t` is present and tradable in the tick-`t` observation and in P2/P3, and is resolved at the start of P1 of tick `t+1` (with a virtual tick `T+1` used by finalisation)."* Pick one and write the sentence; today both A10 and A16 have to guess.

---

## HIGH (a module owner has no way to implement their contract)

**6. Section 5 contains calls that do not typecheck against section 7, and two invariants require data `AccountBook` never receives.**
- `CONTRACTS.md:635` — `accounts.check_invariants(ref_prices)`; §7.9 declares `def check_invariants(self, *, book_view=None, ref_prices=None) -> None`. Keyword-only. A positional call is a `TypeError`.
- `CONTRACTS.md:571` — `exchange.cancel_all(market_id=..., reason=MARKET_RESOLVED)`; §7.8 declares `tick` as a required keyword. `TypeError`.
- **I8** requires *"the owner's per market resting count is `<= max_active_orders_per_market`"* and **I10** requires *"`abs(inventory_qty) <= mm.inventory_max`"*, but `AccountBook.__init__` takes no `MatchConfig` and no `MMConfig`. A06 cannot implement two of the eleven invariants they own.
- `book_view` defaults to `None`, and nothing says what I3 does when it is absent, so A06's "checked every tick" and A09's call will silently disagree on whether I3 ran.

**Fix:** in §5 write `accounts.check_invariants(book_view=exchange.book_view(), ref_prices=state.ref_prices())` and `exchange.cancel_all(tick=tick, market_id=..., reason=CancelReason.MARKET_RESOLVED)`; add `def book_view(self) -> Mapping[str, tuple[Order, ...]]` to `Exchange`; change the `AccountBook` constructor to
```python
def __init__(self, *, agent_ids, market_ids, initial_cash_cents: int,
             mm_initial_cash_cents: int, taker_fee_bps: int,
             max_active_orders_per_market: int, mm_inventory_max: int) -> None
```
and make `book_view` **required** in `check_invariants`.

**7. The market maker cannot see its own inventory.**
`CONTRACTS.md:1094` — `def requote(self, *, tick: int, exchange: Exchange, journal: Journal) -> tuple[Quote, ...]`, while `compute_quote(*, tick, market_id, ref_price, inventory_qty)` needs `inventory_qty` and FR-5.8.3's cap is expressed on it. Inventory lives in `AccountBook.position("MM", market_id)`; `requote` has no accounts handle and `Exchange` exposes no position accessor. A07 will either reach into `exchange._accounts` (private, forbidden by §7) or track inventory itself from trades, which drifts from A06's ledger and breaks I10. **Fix:**
```python
def requote(self, *, tick: int, exchange: Exchange, accounts: AccountBook,
            journal: Journal) -> tuple[Quote, ...]
```

**8. `SettlementApplied` has two owners and one of them cannot emit it.**
`CONTRACTS.md:574` (P1 step 4c) — *"`accounts.apply_settlement(...)` -> one `SettlementApplied` per account"*, but §7.9's `apply_settlement(*, market_id, outcome, mode) -> tuple[SettlementLine, ...]` takes no `journal` and `AccountBook.__init__` has no journal either. Meanwhile §7.11 declares `settle(*, tick, market_id, outcome, accounts, journal, mode) -> tuple[SettlementLine, ...]` in A08's `oracle/settlement.py`, which does have one. A06 and A08 will both write the emission loop, or neither will. **Fix:** delete the emission claim from P1 step 4c and rewrite it as *"`oracle.settlement.settle(tick=..., market_id=..., outcome=..., accounts=..., journal=..., mode=...)` mutates the ledger through `accounts.apply_settlement` and emits one `SettlementApplied` per returned line, in canonical account order. `AccountBook` never emits events."* Add that last sentence to §7.9 as a rule.

**9. `Oracle.resolve` and the runner both own P1 steps 4a-4e.**
`CONTRACTS.md:1130` — `def resolve(self, *, tick, market_id, exchange, accounts, journal) -> ResolutionReport`, returning `cancelled_order_ids` and `settlements`, i.e. it clearly performs 4a-4c itself. Yet §5 P1 lists 4a (`exchange.cancel_all`), 4b (`emit(MarketResolved)`), 4c, 4d and 4e as runner steps. Implemented literally by both A08 and A09 you get two `cancel_all` passes and two `MarketResolved` events. **Fix:** state in §5 that step 4 is a single call — *"`report = oracle.resolve(tick=tick, market_id=mid, exchange=exchange, accounts=accounts, journal=journal)`, which performs 4a, 4b, 4c and 4e; the runner then performs 4d"* — and add `close_market` to the "called by Oracle only" list in §7.8.

**10. `pxe.store` and `pxe.tournament` are a hard import cycle, stated literally in the contract.**
§7 dependency arrow: `tournament <- store` (store may import tournament, tournament may not import store). But `CONTRACTS.md:1527` — `class TournamentOrchestrator: def __init__(self, *, config: TournamentConfig, store: Store)` (tournament imports store) and `CONTRACTS.md:1600` — `def save_task(self, task: MatchTask, *, status: str)` plus `save_ratings(..., records: Sequence[RatingRecord])` (store imports tournament). Add `evolve.collect_failures(store=...)` and it is a three-way tangle. **Fix:** move the pure data carriers `MatchTask`, `TournamentConfig`, `TournamentResult` and `RatingRecord` into `pxe.types` (A01 owns them, everyone imports leftward), leaving only behaviour in `pxe.tournament`. Then the arrow `types <- store <- tournament` holds with no cycle.

**11. `MatchProjection` is built from five types that are never defined.**
`CONTRACTS.md:1388-1392` — `trades: tuple[TradeRecord, ...]`, `orders: tuple[OrderRecord, ...]`, `predictions: tuple[PredictionRecord, ...]`, `signals: tuple[SignalRecord, ...]`, `messages: tuple[MessageRecord, ...]`. Grep: those five names appear exactly once each in the whole repository. A15 invents their fields; A16 (`compute_calibration`), A17 (`compute_descriptors`), A18 (`collusion_index`, all four detectors), A22 (`/metrics`) and A25 all code against fields they cannot see. This is the single largest guess-surface in the document. **Fix:** write the five frozen dataclasses out in full in §7.17 with their exact field names and units, before A15 starts. Also note that `PredictionRecord` (A15), `PredictionRecorded` (A01 event) and `Prediction` (A01 dataclass) are three names for one concept; rename the projection one `PredictionRow` or drop `types.Prediction`, which nothing uses.

**12. Nothing converts an `AgentAction` into the JSON the journal requires.**
`events.AgentActionReceived` declares `predictions: tuple[dict[str, Any], ...]` and `orders: tuple[dict[str, Any], ...]` with *"holding `op`, `market_id`, `side`, `order_type`, `price`, `qty`, `order_id`"*. `AgentAction` holds `tuple[PredictionIntent, ...]` / `tuple[OrderIntent, ...]`. No function anywhere maps one to the other, and the field is named `order_type` in `OrderIntent` but `type` in `schemas/action.v1.json`. A09 and A13 will each write their own mapping; if they differ on key names or on how `None` is encoded, journal hashes differ. **Fix:** add to §7.1 (A01, next to the dataclasses):
```python
def order_intent_to_dict(intent: OrderIntent) -> dict[str, Any]      # journal key names, nulls kept
def prediction_intent_to_dict(intent: PredictionIntent) -> dict[str, Any]
def action_to_payload(action: AgentAction) -> dict[str, Any]         # schemas/action.v1.json shape
```
and state which of the two key spellings (`type` or `order_type`) the journal uses.

**13. `replay_journal` cannot be implemented as specified.**
`CONTRACTS.md:1180` — `def replay_journal(events: Sequence[Event]) -> MatchState`, and `MatchState` holds `config: MatchConfig`, `scenario: ScenarioSpec`, `accounts: AccountBook`, `exchange: Exchange`. Rebuilding those requires turning `MatchStarted.config` back into a `MatchConfig` and `MatchStarted.markets[]` back into `MarketSpec`/`ScenarioSpec`. No such constructor exists (`MarketSpec` has no `from_dict`, `ScenarioSpec` has no `from_journal`). FR-5.1.3 and AC-P1's `pxe match replay` both hang on it. **Fix:** ship the inverses in A01 alongside finding 1's:
```python
def market_spec_from_dict(data: Mapping[str, Any]) -> MarketSpec
def scenario_from_match_started(event: MatchStarted) -> ScenarioSpec
```

**14. Nobody owns building the `RngTree`, so scripted agents have no defined seed.**
`CONTRACTS.md:348` — *"The runner builds the tree"*, and `root = RngTree(config.seed)`. But `MatchRunner.__init__(*, config, world, agents, gateway, journal, match_id)` receives an already-constructed `gateway`, and `ScriptedGateway(*, agents: Mapping[str, ScriptedAgent])` receives already-constructed agents, whose factory is `make_baseline(name, *, agent_id, rng: random.Random, config)` with §7.15 requiring `root.child(f"agent/{agent_id}").substream(f"agent.{agent_id}")`. The tree must therefore exist **before** the runner that is said to build it. On top of that `ScriptedAgent.reset(*, config, rng)` is declared and never called anywhere in §5, so an agent reused across two matches in a tournament carries state and O1 dies silently. **Fix:** state in §3.1 that *"the **caller** (`run_match`, the CLI or the orchestrator) builds `RngTree(config.seed)` and passes it to `MatchRunner(..., rng: RngTree)`; the runner calls `agent.reset(config=config, rng=rng.child(f"agent/{aid}").substream(f"agent.{aid}"))` for every scripted agent at `MatchStarted`, before tick 1"*, and add `rng: RngTree` to `MatchRunner.__init__` and to `run_match`. Also add an anti-vacuous test to §10: two consecutive matches with the same reused agent objects must produce identical journals.

**15. `MatchRanking.brier_ppm` forces the runner to import `metrics`, against the dependency arrow.**
`types.MatchRanking` carries `brier_ppm`, and §5 finalisation step 18/19 has the runner emit `MatchEnded(rankings=[...])`. Brier is defined in §9 as a projection computed by A16 `compute_calibration(projection)` over a `MatchProjection` built by `project(events)` — from the journal the runner has not finished writing. The arrow is `runner <- ... metrics`, so `runner` importing `metrics` is a cycle in the delivery order too (A15/A16 depend on A09's golden journals). **Fix:** either (a) drop `brier_ppm` from `MatchRanking` and put it in the metrics layer only, or (b) state explicitly that the runner accumulates Brier incrementally from its own `PredictionRecorded` emissions with `types.brier_term_ppm` and that A16 must reproduce that number bit-for-bit (and add `test_metrics_calibration.py::test_matches_runner_brier`). Option (a) is cleaner; either way it must be written down.

---

## MEDIUM (real divergence, cheaper to fix)

**16. `pytest` fails with exit code 4 on a clean checkout, so the T1.1 gate is red for all 25 agents.**
`pyproject.toml` sets `addopts = ["--strict-config", ...]` and `asyncio_mode = "auto"`, but `pytest-asyncio` is only in the `dev` extra and is not installed in `.venv`. Verified: `python -m pytest --collect-only` prints `ERROR: Unknown config option: asyncio_mode` and exits `4`. **Fix:** install `pytest-asyncio` in the project venv and add it to the environment bootstrap, or drop the `asyncio_mode` line until A13 lands. The pinned pytest is 9.1.1, so also verify `asyncio_mode` is still the correct key for the version being installed.

**17. `Exchange.begin_tick` is declared and never called.**
`CONTRACTS.md:1021` — `def begin_tick(self, tick: int) -> None      # resets per tick counters`. Section 5 never invokes it, yet `MarkToMarket.tick_volume_qty` (P4 step 12) reads `exchange.tick_volume(market_id)`. Implemented literally, volume accumulates over the whole match. **Fix:** insert as P1 step 0 in §5: *"`exchange.begin_tick(tick)` before `emit(TickStarted, ...)`"*.

**18. The taker fee has two owners with different rounding.**
`matching.MatchPlan.fee_cents` (A05, computed inside `plan_match(..., fee_bps)`) is one aggregate number over all fills; `fees.taker_fee_for(config, *, price, qty)` (A06) is per fill; `TradeExecuted.taker_fee_cents` is per trade. Because `taker_fee_cents` floors, `sum(floor(f_i)) != floor(sum(f_i))` whenever a marketable order walks two price levels, so **I5** (`maker_delta + taker_delta + taker_fee == 0` per trade) and the pre-trade reservation will disagree by a cent. Related: §6.1 says the collateral check runs *"before matching"*, but `plan_match` marks STP cancellations whose released collateral would change affordability, and nothing states whether that release is available to fund the incoming order. **Fix:** in §6.1 write *"the fee is computed per fill as `taker_fee_cents(fee_bps, fill.price, fill.qty)`; `MatchPlan.fee_cents` is the sum of the per fill fees and is informational only"*, and *"the pre-trade check runs before STP cancellations; collateral released by STP is not available to the incoming order"*.

**19. The resolution news never reaches the market maker, so decision 9/12 does not happen.**
§5 P1 step 2 calls `mm.note_news(tick, items)` for info-engine news only; step 4d emits the resolution `NewsPublished(origin="resolution", impact="high")` with no `note_news` call. Decision 12 and the section 12 rationale both assert *"the market maker widens after every resolution (FR-5.8.4)"*. A07 tests `test_post_news_widening` against a behaviour A09 never triggers. **Fix:** append to P1 step 4d: *"...then `mm.note_news(tick=tick, items=(resolution_item,))`"*, or move the `note_news` call to a single point after all P1 news of the tick has been emitted (preferable — one call site, one order).

**20. `schemas/action.v1.json` hardcodes limits that `MatchConfig` makes configurable and advertises to the agent.**
`"orders": { "maxItems": 20 }` and `"predictions": { "maxItems": 8 }`, while `MatchConfig.max_orders_per_action` validates only `>= 1` and is published to the agent as `limits.max_orders_per_action` in every observation. A tournament TOML with `max_orders_per_action = 40` produces observations telling the agent 40 and a `--json-schema` rejecting at 21. `qty` is also capped at `100000` in the schema with no corresponding engine constant. **Fix:** either clamp in `MatchConfig.__post_init__` (`if not 1 <= max_orders_per_action <= 20: raise InvalidConfigError`) and say in §8.2 that the schema is the hard ceiling, or make A11's `schema_registry` patch `maxItems` from the config before handing the schema to the CLI. State which. Add `MAX_ORDER_QTY = 100_000` to `types` so A05 and A11 reject the same thing.

**21. P2 and P3 both validate market and order liveness, with different event types and a stale snapshot.**
§7.14's table has A11 reject `UNKNOWN_MARKET` and `UNKNOWN_ORDER` (emitting `AgentActionRejected` in P2), while §7.8's `Exchange.submit`/`cancel` reject `MARKET_NOT_OPEN`, `UNKNOWN_ORDER`, `NOT_ORDER_OWNER` (emitting `OrderRejected` in P3). `resting_order_ids` is captured in P2, but by P3 the MM requote and earlier agents in the shuffle may have filled or STP-cancelled that order, so a cancel validated in P2 legitimately fails in P3. Two workstreams will disagree on which rejection an integrity detector or the UI should count. **Fix:** add to §7.14: *"P2 validation is structural and advisory: `resting_order_ids` is used only to catch ids the agent never owned. Liveness is authoritative in P3. Only `Exchange` emits `OrderRejected`; `validate_action` never rejects on liveness, and a cancel of an already-gone order yields `OrderRejected(reason=UNKNOWN_ORDER)` in P3, not `AgentActionRejected`."*

**22. `ScenarioSpec` and `MatchConfig` duplicate three fields with no precedence rule.**
`ticks_total`, `talking_mode` and `liquidity_profile_name` exist in both, and `generate_world(*, template_id, seed, ticks_total=48, liquidity=..., talking_mode=..., held_out=...)` sets the scenario copy while the orchestrator's TOML sets the config copy. `MatchRunner.__init__(*, config, world, ...)` receives both and nothing says which wins. Worse, `MatchConfig.mm` (an `MMConfig`) and `ScenarioSpec.liquidity_profile_name` can name different presets. **Fix:** add one line to §7.12: *"`MatchRunner.__init__` raises `InvalidConfigError` when `config.ticks_total != world.scenario.ticks_total`, `config.talking_mode != world.scenario.talking_mode`, or `config.mm != liquidity_profile(world.scenario.liquidity_profile_name).mm`. `MatchConfig` is authoritative; the scenario copies are informational."*

**23. The claimed one-to-one mapping between `errors.code` and `RejectReason` is false, and no converter exists.**
`CONTRACTS.md:293` — *"The `code` values are re-exported as `pxe.types.RejectReason` members for everything that can appear in a journal."* In fact `InvalidOrderError.code = "INVALID_ORDER"` has no `RejectReason` member, and `INVALID_PRICE`, `INVALID_QTY`, `INVALID_SIDE`, `INVALID_TYPE`, `MISSING_FIELD`, `UNKNOWN_MARKET`, `TOO_MANY_ORDERS_IN_ACTION`, `TOO_MANY_PREDICTIONS`, `DUPLICATE_PREDICTION`, `INVALID_PROBABILITY`, `MESSAGE_TOO_LONG`, `TALKING_MODE_OFF` have no exception. A05 catching `InvalidOrderError` to fill `OrderRejected.reason` has nothing to put there. **Fix:** add `RejectReason.INVALID_ORDER` and ship the converter in A01:
```python
def reject_reason_of(error: PxeError) -> RejectReason   # raises on an unmapped code
```
plus a test in `test_types.py` asserting every `ExchangeError` subclass maps.

**24. File ownership overlaps inside three packages.**
§1 says *"Directory `__init__.py` files are owned by the workstream that owns the directory"*, yet `runner/observation_builder.py` (A10) and `runner/action_validator.py` + `runner/schema_registry.py` (A11) sit in a directory whose `__init__.py` is A09's, and `tournament/report.py` (A23) sits in A19's. The moment A10 or A23 needs a re-export, they edit a file they do not own, which rule 1 forbids. `runner/__init__.py` re-exporting `match_runner` would also create an import cycle for `observation_builder`, which imports `runner.state`. **Fix:** add to §1: *"`runner/__init__.py`, `tournament/__init__.py` and every other shared `__init__.py` contain a module docstring and nothing else. Submodules always import by full path (`from pxe.runner.state import MatchState`), never from the package."*

**25. Two of the six run artefacts have no writer in any public API.**
§4.6 assigns `observations.jsonl` to A10 and `metrics.json` to A15/A16/A17, but §7.13 exposes only pure functions (`build_observation`, `observation_to_json`, `observation_hash`, ...) and §7.17 exposes only `compute_*`. Nobody writes the files, and A22's `/api/matches/{id}/metrics` reads one of them. **Fix:** add `def write_observation(path: Path, obs: Observation) -> None` to §7.13 and `def write_metrics(path: Path, projection: MatchProjection) -> None` to §7.17, or reassign both files to A09 in §4.6 and say so.

**26. `harness_key` and `config_hash` are used by four workstreams and produced by none.**
`types.HarnessConfig.config_hash` is documented as *"Computed by :mod:`pxe.gateway.protocol`"*, but §7.16's public API for that module lists no such function. §2.2 defines the harness key format `<harness_id>@<version>` "assigned by gateway", and `MatchTask.harness_keys`, `RatingRecord.harness_key`, `EliteCell.harness_key`, `HallOfFame.freeze` and `collect_failures(harness_key=...)` all consume it. Three agents will write three key builders and the TrueSkill leaderboard will fragment. **Fix:** put both in A01's `types.py` (they are pure and everyone needs them):
```python
def harness_key(harness: HarnessConfig) -> str            # f"{harness_id}@{version}"
def harness_config_hash(harness: HarnessConfig) -> str    # blake2b over canonical_json of the 6 fields
```

---

## LOW (fix now because it is one line, not because it will explode)

**27.** `MM` quotes go through `Exchange.submit`, which enforces the collateral check of §6.1 and can therefore emit `OrderRejected(agent_id="MM")`. §5 step 9 and §7.10 never mention this path, and AC-P9 (*two sided on ≥95% of ticks*) fails silently if the MM is ever short of free cash. **Fix:** state in §7.10 that a rejected MM quote emits `OrderRejected` and sets the corresponding `MMQuoted` side to `null`, and add it to `test_market_maker.py::test_guaranteed_liquidity_with_mute_agents`.

**28.** `sorted_ids`, `stable_key` and `ordered` are in the §7.1/§7.3 public API but missing from `types.__all__` / `rng.__all__` (verified: `"sorted_ids" in pxe.types.__all__` is `False`). With `no_implicit_reexport = true` in mypy this is a live trap for anyone re-exporting them. **Fix:** add all three.

**29.** `World.news_plan: tuple[tuple[int, str, NewsImpact, bool], ...]` carries a single `market_id`, but `NewsItem.market_ids` is a tuple and FR-5.2.1's whole point is correlated markets. A single news item can never reference two correlated markets, which removes the coherence-arbitrage signal the PRD asks for. **Fix:** `tuple[tuple[int, tuple[str, ...], NewsImpact, bool], ...]`, or better, a named frozen dataclass `NewsPlanItem` so A03 and A04 stop passing positional 4-tuples across a workstream boundary.

**30.** `InfoEngine.__init__(*, world, profiles: Mapping[str, InfoProfile], ...)` — §2.3 forbids deriving output from dict iteration, and `signals_for_tick` must loop over agents. **Fix:** add to §7.6: *"`profiles` is iterated only via `sorted_ids(profiles.keys())`."* Same sentence is needed for `ClaudeCliGateway(*, harnesses: Mapping[...])` and `ScriptedGateway(*, agents: Mapping[...])`.

**31.** `types.Incident.detail: tuple[tuple[str, Any], ...]` versus `events.IncidentRaised.detail: dict[str, Any]` — two shapes for one field, and A18 must convert in both directions for `write_incidents` and for `IncidentKind.TECHNICAL` journalling. Pick the tuple form (it is the one that survives `canonical_json` deterministically) in both places.

**32.** The bankruptcy rule diverges from the PRD, and the doc's own rule says the PRD wins. §5 P4 step 14 freezes on `equity_cents <= config.bankruptcy_equity_floor_cents` (default `0`); FR-5.5.5 says *"Faillite (cash et collatéral **libres** épuisés)"*. Since `cash_cents >= 0` is invariant I9 and long positions have non-negative value, equity reaches 0 essentially never, so `AgentFrozen` is dead code and `test_match_runner.py::test_bankruptcy_freezes_agent` will need a contrived setup to pass. **Fix:** freeze on `free_cash_cents(a) <= floor and no resting orders and every position flat`, or state explicitly in §12 that you are overriding the PRD here and why.
