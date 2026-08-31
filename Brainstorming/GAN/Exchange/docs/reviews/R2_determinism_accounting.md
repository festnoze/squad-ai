I read the PRD in full, then `docs/CONTRACTS.md` (1931 lines), `types.py`, `events.py`, `rng.py`, `errors.py`, both schemas, `pyproject.toml` and `README.md`. I also executed the code where a claim was checkable. Findings ranked by severity.

---

## 1. BLOCKER (verified by execution) - `MatchConfig` cannot be journalled: it contains a float

`src/pxe/types.py:1552`
```python
    agent_timeout_s: float = 60.0
```
`docs/CONTRACTS.md:296` says `MatchConfig` is journalled verbatim in `MatchStarted.config`; `events.py:341` types it `config: dict[str, Any]` with docstring "Canonical mapping of the full `MatchConfig`". `canonical_json` rejects every float.

Verified:
```
CANONICAL_JSON RAISES: NonCanonicalValueError [NON_CANONICAL_VALUE] floats are forbidden in the journal
  (path='$.agent_timeout_s', value='60.0')
```
The first event of every match crashes the engine. Worse, the field's own docstring (`types.py:1530`) says "Lives outside the pure engine and is never journalled", contradicting the class docstring two lines up. A wall-clock timeout inside the hashed config would also make the journal hash depend on a gateway setting, i.e. two runs with the same seed and different timeouts would hash differently.

**Fix:** delete `agent_timeout_s` from `MatchConfig` (it duplicates `GatewayConfig.timeout_s`, which §2.6 already declares un-journalled), and add to CONTRACTS §2.6: "`MatchConfig` contains no float field. `canonical_json(asdict(config))` is asserted in `tests/test_types.py::test_config_is_canonical`."

---

## 2. CRITICAL - the canonical account order is specified three different ways; the journal ordering is undefined

Three sources disagree about the order of the `SettlementApplied` and `PositionSnapshot` loops, which directly sets `seq` numbering and therefore the journal hash:

* `docs/CONTRACTS.md:278` - "ranked agents ascending numeric suffix, then `MM`, then `FEES`. This is the *canonical account order*, used by `AccountBook.account_ids()`" and §2.3 mandates `pxe.types.sorted_ids` for canonical ordering.
* `src/pxe/events.py:944` (`PositionSnapshot` docstring) - "agents first then ``FEES`` then ``MM``".
* `src/pxe/types.py` `sorted_ids` key `(1, value, 0)` for non `M`/`A` ids. Verified: `sorted_ids(["A1","A2","MM","FEES"]) -> ('A1', 'A2', 'FEES', 'MM')`.

So the helper the contract points at produces the order the contract forbids. A06 (implements `account_ids()`) and A09 (writes the P4 loop) will each pick one and the golden hashes will not reproduce.

**Fix:** pick one, then make `sorted_ids` unable to produce the other. Replace the `sorted_ids` key with an explicit rank and add a dedicated helper:

```python
_ACCOUNT_RANK = {MM_ACCOUNT_ID: 1, FEES_ACCOUNT_ID: 2}

def canonical_account_order(ids: Sequence[str]) -> tuple[str, ...]:
    """Canonical account order: ranked agents ascending, then MM, then FEES."""
    return tuple(sorted(ids, key=lambda a: (_ACCOUNT_RANK.get(a, 0),
                                            int(a[1:]) if a[0] == "A" else 0, a)))
```
Add `canonical_account_order` to §7.1 and §2.3, forbid `sorted_ids` on account ids, and fix the `PositionSnapshot` docstring.

---

## 3. CRITICAL - `mm_initial_cash_cents` is load bearing but exists in no dataclass and is in no event

`docs/CONTRACTS.md:698` (invariant I2), `:709` ("it is a config value ... and is part of `MatchStarted.config`"), `:1042` (`AccountBook.__init__(..., mm_initial_cash_cents: int, ...)`) and decision 16 all depend on it. Verified by grep: it appears in no `.py` file. `MatchConfig` and `MMConfig` have no such field.

Three consequences, all in my lens:
* I2 cannot be evaluated, so the one invariant that catches money creation is dead on arrival.
* It is not journalled, so `replay_journal` (FR-5.1.3) cannot re-check I2 from the journal alone.
* `MatchProjection` carries `initial_cash_cents` (agents') but no MM starting cash, so `mm_pnl_cents` (the FR-5.8.5 "cost of liquidity", required in every report) cannot be recomputed from the journal - it can only be copied out of `MatchEnded`, which defeats §9's "every metric is computed from a `MatchProjection`".

**Fix:** add to `MatchConfig`, after `initial_cash_cents`:
```python
    mm_initial_cash_cents: int = 10_000_000   # 10x an agent, FR-5.8.5 / invariant I2
```
add `mm_initial_cash_cents` to `MatchProjection` (read from `MatchStarted.config`), and state I2 as `total_cash == n_agents * initial_cash_cents + mm_initial_cash_cents + 0` with the `FEES` account starting at 0.

---

## 4. CRITICAL - nothing forces LF on the journal writer, and the primary dev platform is Windows

`docs/CONTRACTS.md:467` asserts "Files are UTF-8, no BOM, LF line endings" and §4.3 asserts "the digest of the events equals the digest of the `journal.jsonl` bytes". But §7.4's writer signature is only
```python
    def __init__(self, match_id: str, path: Path | None = None, *, buffer_size: int = 256) -> None
```
with no encoding or newline requirement. On Windows, `open(path, "w")` translates `\n` to `\r\n`. Then `journal_hash(events)` (which hashes `"...\n"`) and `blake2b(open(path,"rb").read())` differ, AC-P1's "bit identical journals" fails between a Windows box and a Linux box, and `journal_hash_from_lines` silently re-normalises the difference away so the mismatch is invisible until you diff bytes.

**Fix:** make the mode part of the contract, not prose:
```python
    def __init__(self, match_id: str, path: Path | None = None, *, buffer_size: int = 256) -> None
        """Opens path with open(path, "w", encoding="utf-8", newline="\n"). Never text mode default."""
```
and add `tests/test_journal.py::test_file_bytes_hash_equals_journal_hash` asserting `hashlib.blake2b(path.read_bytes(), digest_size=32).hexdigest() == journal.hash()` plus `b"\r" not in path.read_bytes()`, marked `determinism`.

---

## 5. HIGH - the P3 fairness shuffle is specified over two different lists, and the named test contradicts one of them

`docs/CONTRACTS.md:411-412` (§3.4):
```python
order = shuffle_seeded(runner_rng.fresh_substream(f"runner.tick_shuffle.{tick}"),
                       sorted_ids(ranked_agent_ids))
```
`docs/CONTRACTS.md:614-615` (§5, P3 step 10):
```python
10. `order = shuffle_seeded(rng.fresh_substream(f"runner.tick_shuffle.{tick}"),
    sorted_ids(active_ranked_agent_ids))`.
```
`ranked_agent_ids` and `active_ranked_agent_ids` differ as soon as one agent is frozen, and `MatchState.active_agent_ids()` is documented as "ranked, not frozen". Shuffling a shorter list yields a different permutation of the survivors, so the two spellings produce different execution orders and different journals for the same seed.

Additionally the traceability test named at `docs/CONTRACTS.md` §11.2 FR-5.1.5, `test_tick_shuffle_depends_only_on_seed_and_tick`, is literally false under the §5 spelling: the permutation depends on `(seed, tick, frozen_set)`.

**Fix:** shuffle the full seat list, then filter. Replace both occurrences with:
```python
order = [a for a in shuffle_seeded(rng.fresh_substream(f"runner.tick_shuffle.{tick}"),
                                   sorted_ids(state.ranked_agent_ids()))
         if a not in state.frozen_agent_ids]
```
This keeps the test name true and makes the permutation depend on `(seed, tick)` alone.

---

## 6. HIGH - STP can release the same collateral twice

`RejectReason`/`CancelReason` defines `STP = "stp"` (`types.py:330`), §4.5 defines `order_cancelled` as emitted "per order leaving the book" carrying `released_cents`, and `STPCancelled` also carries `released_cents` (`events.py`). But §5 P3 step 11 says `submit` "emits `OrderPlaced` then any `STPCancelled` and `TradeExecuted`" - no `OrderCancelled`.

So an STP-cancelled resting order either leaves the book without an `OrderCancelled` (breaking §4.5's own rule, and breaking any projection that reconstructs resting orders from `OrderPlaced` minus `OrderCancelled`), or both events are emitted and any projection summing `released_cents` credits the collateral twice. `CancelReason.STP` existing while step 11 never emits it is the tell that two implementers will choose differently.

**Fix:** state it once, normatively. In §5 step 11:
> `op == "place"` -> `exchange.submit(...)`, which emits `OrderPlaced`, then for each self cross one `OrderCancelled(reason=STP, released_cents=...)` immediately followed by one `STPCancelled(released_cents=0)`, then the `TradeExecuted` events.

and drop `released_cents` from `STPCancelled` (or keep it and set `released_cents=0` on `OrderCancelled`). Add the same sentence for the freeze path: `AgentFrozen.cancelled_order_ids` is a cross reference only, the money moves in the preceding `OrderCancelled` events.

---

## 7. HIGH - observations are in the journal hash after all, so the observation builder is inside AC-P1

Decision 11 and the summary claim "observations are hashed, not journalled ... keeps builder version bumps from moving a journal hash". The hash *is* the journal:

`src/pxe/events.py` `ObservationBuilt`:
```python
    obs_hash: str
    obs_bytes: int
```
Any change by A10 to `observation_to_json` - a compaction lever, one more depth level, a shorter `body` truncation, a renamed key - changes `obs_hash` and `obs_bytes` for every tick of every match, and therefore every golden hash in `tests/golden/`. With scripted agents the observation content has zero effect on any engine decision, so AC-P1 is being made hostage to a presentation module.

Second, smaller point: `obs_bytes` is the length of `stable_json`, which permits floats (`signals[].value` and `my_last_prediction` are `"type": "number"` in `schemas/observation.v1.json`). Those particular floats are safe (they derive from `_milli`/`_ppm` integers divided by a power of ten, which is exactly rounded), but the contract as written permits any float there, and one float that is not integer-derived puts float formatting inside the journal hash.

**Fix:** either drop `obs_hash`/`obs_bytes` from the event and put them in `observations.jsonl` next to the payload, or keep `obs_hash` and add a hard rule to §8.1:
> The observation JSON contains no float that is not an exact quotient of an integer by a power of ten. `tests/test_observation_builder.py::test_no_free_floats` asserts every numeric leaf satisfies `Fraction(x).limit_denominator(10**6) == Fraction(x)`.

and state in §12 decision 11 that a bump of `pxe.runner.observation_builder` *does* require regenerating the golden hashes.

---

## 8. HIGH - the bankruptcy rule of FR-5.5.5 is unreachable with the shipped default

`src/pxe/types.py:1556`
```python
    bankruptcy_equity_floor_cents: int = 0
```
`docs/CONTRACTS.md` §5 P4 step 14: "any ranked, non frozen agent with `equity_cents <= config.bankruptcy_equity_floor_cents` is frozen".

Proof that this never fires: invariants I4/I9 give `cash >= reserved >= 0`. For a short of `n` on market `m`, reserved includes `100n` while equity includes `n * ref_m >= -99n`, so that market contributes at least `+n` to `cash - reserved`. For a long of `n`, reserved contributes 0 and equity contributes `n * ref_m >= n`. Hence `equity >= free_cash + (number of contracts held) > 0` for any agent holding anything, and `equity == cash >= 0` when flat. Equity reaches 0 only on exact-to-the-cent ruin while flat. `test_match_runner.py::test_bankruptcy_freezes_agent` can only pass by overriding the config, so the shipped arena has no bankruptcy, and FR-5.5.5's freeze plus the `AgentFrozen` event plus decision 9 (frozen agents get no observation) are all dead paths.

Note this is not just a tuning nit: the PRD's wording is "cash **et collatéral libres** épuisés", i.e. free cash exhausted, not equity at zero. The contract silently substituted a different predicate.

**Fix:** state the PRD predicate. In §5 P4 step 14:
> A ranked, non frozen agent is frozen when `free_cash_cents(a) < PRICE_MIN` **and** it holds no non flat position on any open market (it can no longer place any order, nor liquidate anything), or when `equity_cents(a) <= config.bankruptcy_equity_floor_cents`.

and change the default to something reachable, e.g. `bankruptcy_equity_floor_cents: int = 10_000` (1 % of initial cash), documented in §12 as a tuning knob.

---

## 9. HIGH - `check_invariants` has two contradictory signatures and I8/I10 are not computable from an `AccountBook`

`docs/CONTRACTS.md` §5 P4 step 15: `accounts.check_invariants(ref_prices)` (positional).
`docs/CONTRACTS.md` §7.9:
```python
    def check_invariants(self, *, book_view: Mapping[str, Sequence[Order]] | None = None,
                         ref_prices: Mapping[str, int] | None = None) -> None
```
Keyword-only. The §5 call raises `TypeError`, which §2.4 forbids library code from producing.

Beyond the signature, three of the eleven predicates cannot be evaluated from what `AccountBook` is given:
* **I8** needs `max_active_orders_per_market`; `AccountBook.__init__` takes only `agent_ids, market_ids, initial_cash_cents, mm_initial_cash_cents, taker_fee_bps`.
* **I10** needs `mm.inventory_max`; `AccountBook` never sees `MMConfig`.
* **I5, I6, I11** are event-level or end-of-match predicates, not state predicates, yet §6.2 says `check_invariants` "asserts all of these" and §5 step 15 says it "runs on **every** tick".

Since §5 step 15 is what makes I1..I11 real (rather than test-only), this gap silently reduces the per-tick check to I1/I2/I3/I4/I7/I9.

**Fix:** one signature, one owner:
```python
    def check_invariants(self, *, ref_prices: Mapping[str, int],
                         book_view: Mapping[str, Sequence[Order]],
                         config: MatchConfig, mm_inventory: Mapping[str, int]) -> None
        """Raises InvariantViolationError naming the first breach among I1, I2, I3, I4, I7, I8, I9, I10."""
```
and move I5/I6 to `Exchange.apply_trade` / `AccountBook.apply_settlement` (checked at the moment they happen) and I11 to `MatchRunner.finalise()`. Update the §6.2 table with a "checked by / checked when" column.

---

## 10. MEDIUM-HIGH - the observation schema makes a legal scenario crash the engine

`schemas/observation.v1.json`:
```json
    "markets": { "type": "array", "minItems": 1, "maxItems": 8, ... }
```
and `marketBlock.status` is `{"const": "open"}`. §8.1: "Resolved markets disappear from `markets` after their resolution tick."

FR-5.2.3 allows every market to carry its own resolution tick in `1..T`. A world where the last market resolves at tick `T-3` produces an observation with `markets: []` at ticks `T-2..T`, which fails `validate_observation`, which raises `ObservationValidationError` (`errors.py`), which §2.4 says the engine must not swallow. The match aborts. `ScenarioSpec.__post_init__` only checks `resolution_tick <= ticks_total`, so nothing rejects such a world up front either.

**Fix:** `"minItems": 0` in the schema, plus a `ScenarioSpec` guard `max(m.resolution_tick for m in markets) == ticks_total` if you prefer to forbid the case, plus a §5 finalisation rule for what P2 does when an agent has nothing to predict (skip the gateway call entirely, like a frozen agent).

---

## 11. MEDIUM-HIGH - `rng.py` overclaims cross-platform reproducibility for its own distribution helpers

`src/pxe/rng.py:10-13`
```
* Reproducible across processes, machines, OSes and CPython 3.11+ patch levels.
  The only primitives used are :func:`hashlib.blake2b` (stable by definition)
  and :class:`random.Random`, whose Mersenne Twister seeding from an integer is
  part of CPython's documented, frozen behaviour.
```
That is false for four of the exported helpers:
* `normal` -> `rng.gauss`, which calls `_cos`, `_log`, `_sqrt` from libm. `beta` -> `rng.betavariate` (libm, and CPython has changed this function's algorithm in the past). `lognormal` -> `math.exp`.
* libm transcendentals are not bit-identical across glibc / msvcrt / macOS libm versions. Every latent value that lands within one ulp of a half-`_milli` boundary quantises differently, and the whole world diverges from there.
* `shuffle_seeded` delegates to `random.Random.shuffle`, whose algorithm is an implementation detail (CPython already changed its signature in 3.11). If it ever changes, every golden hash moves and the failure looks like a determinism bug rather than an interpreter upgrade.

Only `random()` and `getrandbits()` are documented, frozen behaviour.

**Fix:** implement the permutation and the distributions inside `pxe.rng` on top of `getrandbits` only, so the algorithm is versioned by you:
```python
def shuffle_seeded(rng: random.Random, items: Sequence[T]) -> list[T]:
    """Fisher-Yates using randbelow only. Pinned here so a CPython change cannot move a journal hash."""
    out = list(items)
    for i in range(len(out) - 1, 0, -1):
        j = _randbelow(rng, i + 1)
        out[i], out[j] = out[j], out[i]
    return out
```
and either implement `normal` by an inverse-CDF rational approximation using only `+ - * /` (IEEE 754 exactly rounded, hence bit identical everywhere), or amend the docstring to state that `normal`/`lognormal`/`beta` are reproducible **on one platform only** and that world generation must quantise them through `milli_from_float` with a documented residual risk. Then AC-P1's "two machines" clause needs the same caveat, or it is not honest.

---

## 12. MEDIUM - market cancellation does not restore the cash the PRD says it restores, and no invariant guards it

FR-5.4.5: "l'annulation dénoue toutes les exécutions et restitue le cash." The contract implements it as `apply_settlement(market_id=..., outcome=None, mode="unwind")` producing one `SettlementLine` per account.

`Position.cost_basis_cents` (types.py) makes the position leg computable (`cash_delta = +cost_basis_cents`, and it sums to zero across accounts because each trade contributes `+pq` to the buyer and `-pq` to the seller). But taker fees already routed to `FEES` are never reversed, so the unwind is not integral: an agent that traded and got cancelled is strictly poorer than before the market existed, by the fees it paid. With `taker_fee_bps = 0` (the default) this is invisible, and it will surface only when someone turns fees on.

More importantly, the zero-sum property of the unwind rests entirely on `sum over accounts of cost_basis_cents(a, m) == 0`, which is **not** in the I1..I11 list. Nothing catches a cost-basis drift, and cost basis is the only thing that makes an unwind computable.

**Fix:** add to §6.2:

| **I12** | for every market `m`: `sum over all accounts of cost_basis_cents(a, m) == 0` | unwind (FR-5.4.5) is zero sum |

and add to §7.9: `apply_settlement(..., mode="unwind")` also emits a `FEES` line refunding `sum of taker fees paid on that market`, so I6 holds and the PRD's "restitue le cash" is literal. That requires the `AccountBook` to track `fees_paid_cents` per `(account, market)`; state it in the `AccountState` docstring.

---

## 13. MEDIUM - the README promises reproducible LLM journals; the contract makes that impossible

`README.md`:
> Provider traces (cost, latency, token counts, retries) land in `runs/<match_id>/llm_trace.jsonl`. They are deliberately **not** part of the journal, so an LLM match still hashes reproducibly for everything the engine decided.

Not true, and the contract shows why: `AgentTimedOut(agent_id, reason)` **is** a journal event, and whether it fires is a wall-clock decision (`GatewayConfig.timeout_s`) and a budget decision (`BudgetTracker` raising `BudgetExceededError` mid-match). A slow provider run and a fast one on the same seed produce different `seq` streams from the tick of the first timeout onwards, and every subsequent event shifts. The same applies to `AgentActionReceived.rationale`, which is verbatim model text.

**Fix:** reword README to "the engine's decisions are a deterministic function of the actions it received; the journal of an LLM match is reproducible only when replayed against the recorded actions", and add to CONTRACTS §3: "AC-P1 applies to scripted matches only. For an LLM match, determinism is guaranteed by `replay_journal`, not by re-running." State this in §12 decision 8, which currently claims the opposite.

---

## 14. MEDIUM - the STP release versus solvency check ordering is load bearing and unspecified

§6.1: "Pre-trade check for a submitted order, evaluated **before** matching". §5 P3 step 11: submit "emits `OrderPlaced` then any `STPCancelled`".

Consequence: an agent resting a sell of 100 at 60 (reserved `40 * 100 = 4000`) and then sending a buy of 100 at 61 (needs `61 * 100 = 6100`) is rejected for `INSUFFICIENT_COLLATERAL` if it has under 6100 free, even though the STP cancel that the same submission triggers would have freed 4000 first. A different implementer will naturally run STP detection first (it is a book scan, before matching) and accept the same order. Same seed, two journals.

**Fix:** add one sentence to §6.1 after the accept condition:
> The pre-trade check is evaluated against `free_cash_cents(a)` **before** any STP cancellation is applied. Collateral released by an STP cancellation is never available to the order that caused it. `tests/test_exchange_stp.py::test_stp_release_is_not_available_to_the_incoming_order` pins this.

---

## 15. MEDIUM - `MMConfig.half_spread_cents` silently ignores the post-news widening

`src/pxe/types.py`
```python
    @property
    def half_spread_cents(self) -> int:
        """Half spread rounded up, so an odd spread never narrows."""
        return (self.base_spread_cents + 1) // 2
```
§7.10 normative arithmetic is `half = ceil(spread / 2)` with `spread = base_spread * (widen_multiplier if widened else 1)`. The property computes half of the **base** spread only. A07 reading §7.1's public helper list and reaching for `config.half_spread_cents` gets a market maker that never widens, and `test_market_maker.py::test_post_news_widening` (FR-5.8.4) fails in a way that looks like a market-maker bug rather than a helper trap.

**Fix:** make the parameter explicit and remove the trap:
```python
    def half_spread_cents(self, *, widened: bool = False) -> int:
        """Half spread rounded up. FR-5.8.4: pass widened=True during the widening window."""
        spread = self.base_spread_cents * (self.widen_multiplier if widened else 1)
        return (spread + 1) // 2
```

---

## 16. MEDIUM - `pytest` does not run at all with the committed config

Verified:
```
ERROR: Unknown config option: asyncio_mode
```
`pyproject.toml:80` sets `asyncio_mode = "auto"` under `[tool.pytest.ini_options]` while `--strict-config` (line 67) is on and `pytest-asyncio` is **not** installed in `.venv` (installed: pytest 9.1.1, pytest-cov, hypothesis, jsonschema). The architect's claim "`pytest --collect-only` reads the config cleanly" does not hold in this environment; T1.1's exit gate (`make test` green) is red on day one.

Note also that `pytest-asyncio` 0.23 is pinned in dev extras but pytest 9.1.1 is installed, and `filterwarnings = ["error::DeprecationWarning:pxe.*"]` will make any deprecation inside `pxe` a hard failure - fine, but combined with an unpinned pytest major this is a fragile gate.

**Fix:** install `pytest-asyncio` in `.venv` (or remove the `asyncio_mode` line until A13 lands), and pin `pytest>=8.1,<10` in `[project.optional-dependencies].dev`.

---

## 17. MEDIUM - `pnl_pct_bps` uses floor division on a signed value

`docs/CONTRACTS.md` §9: `pnl_bps = pnl_cents * 10_000 // initial_cash_cents`.

Floor division rounds toward minus infinity for negatives: a loss of 1 cent on 1 000 000 reports `-1` bps, a gain of 1 cent reports `0`. Every loss is systematically overstated by up to one bps and every gain understated. `pnl_pct_bps` sits on `MatchRanking`, in `MatchEnded.rankings`, i.e. in the journal, and it feeds the reports. The same asymmetry applies to `max_drawdown_bps`.

`round_half_up` exists precisely for this and §2.1 already bans `round()` for exactly this class of surprise.

**Fix:** in §9 and in `metrics/performance.py`:
```
pnl_bps = round_half_up(pnl_cents * 10_000 / initial_cash_cents)
```
or, to stay integral, `(pnl_cents * 20_000 + sign * initial_cash_cents) // (2 * initial_cash_cents)`. State the choice; do not leave `//` on a signed numerator.

---

## 18. LOW-MEDIUM - an I4 breach surfaces as a config error, with the wrong CLI exit code

`src/pxe/types.py` `AccountState.__post_init__`:
```python
        if self.reserved_cents < 0 or self.reserved_cents > self.cash_cents:
            raise InvalidConfigError("reserved out of range", ...)
```
That is invariant I4 (`0 <= reserved <= cash`) enforced in a dataclass constructor with `InvalidConfigError` (code `INVALID_CONFIG`). §7.22 maps exit code `4` to "invariant violation" and `1` to "user error", so a genuine accounting bug exits `1` and looks like the operator's fault. It also fires on any legitimately transient intermediate state during a settlement (debit the short before releasing its collateral), forcing A06 into an awkward construction order for a reason that is invisible from the signature.

**Fix:** `raise InvariantViolationError("I4: reserved exceeds cash", account_id=..., reserved=..., cash=...)` and note in the docstring that `AccountState` is a *snapshot* type, so it must only be constructed at a consistent point.

---

## 19. LOW - dead branch in `Event.from_dict` type coercion

`src/pxe/events.py` `_coerce`:
```python
    if origin is Union or str(origin) == "types.UnionType":
```
Verified: `get_origin(int | None)` is the class `types.UnionType`, whose `str()` is `"<class 'types.UnionType'>"`, never `"types.UnionType"`. Every `X | None` field therefore falls through to the final `return value`. Harmless today because every optional field is `int | None` or `str | None`, but the moment someone adds an optional `StrEnum` field (e.g. `outcome: Outcome | None` on a settlement event), `from_dict` returns a raw `str` and round-trip equality tests pass while type checks lie.

**Fix:** `import types` and test `origin is Union or origin is types.UnionType`.

---

## 20. LOW - contract-versus-code drift, each of which will cost someone an afternoon

* `src/pxe/rng.py` `__all__` omits `stable_key` and `ordered`, which §7.3 declares public. With `no_implicit_reexport = true` in mypy, importing them fails type checking.
* `runner.agent_order` is registered in `SUBSTREAMS` but nothing uses it (§3.4 and §5 both use `runner.tick_shuffle.<tick>`). A dead registered name is an invitation to a second, differently seeded shuffle.
* `IncidentRaised.detail: dict[str, Any]` versus `types.Incident.detail: tuple[tuple[str, Any], ...]`. The tuple form exists precisely so the ordering is stable; the event form loses that (recovered only because `canonical_json` sorts keys). Align them on the tuple form.
* `types.prob_from_ppm` and `float_from_milli` use the builtin `round()`, which §2.1 bans outright ("`round()` is banker's rounding and is banned"). Non load bearing here, but it is the anchor module violating its own rule in the file everyone will copy from.
* `schemas/action.v1.json` hardcodes `"orders": {"maxItems": 20}` and `"predictions": {"maxItems": 8}` while `MatchConfig.max_orders_per_action` is configurable (`>= 1`, default 20) and `ObservationLimits.max_orders_per_action` is echoed to the agent. A tournament setting 30 gets schema rejections the validator table in §7.14 never explains. Either freeze `max_orders_per_action` at 20 in `MatchConfig.__post_init__` or generate the schema from the config.
* §5 P2 step 7 emits `PredictionRecorded` inside each agent's block (step c), while `events.py` `PredictionRecorded`'s docstring says "Emitted for every agent and every market ... in ascending `(agent_id, market_id)` order", which reads as one contiguous block. The relative order of `PredictionRecorded` and `MessagePosted` differs between the two readings, which shifts every subsequent `seq`. Pick one and say it in both places.

---

## What I checked and found sound

FR-5.5.1 as split by decision 3 is arithmetically exact: a resting sell reserves `(100 - p) * q`; on fill the seller receives `p * q` and the position reserve becomes `100 * q`, so free cash moves by exactly `-(100 - p) * q` in both states. The buy leg is trivially exact. Decision 4 (no netting) is strictly conservative and never under-collateralises.

The fee reserve is safe under partial fills: `sum_i floor(bps * p_i * q_i / 10^4) <= floor(bps * 100 * sum_i q_i / 10^4) = max_taker_fee_cents(bps, q)`, because `sum floor(x_i) <= floor(sum x_i)` and `p_i <= 100`. No under-reservation is possible.

Settlement is zero-sum given I1, and the resolution ordering in P1 step 4 (cancel resting orders, then resolve, then settle) releases order collateral before the position leg, which is the only order that keeps I4 true throughout.

I10's suppression rule (`inventory + q > I_max` suppresses the bid) does bound `|inventory|` by `I_max` even when both quotes fill in the same tick, since each side moves inventory by at most `q` in one direction.
