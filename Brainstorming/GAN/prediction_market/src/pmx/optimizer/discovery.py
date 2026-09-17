"""Bounded strategy discovery, with train-only proposals and frozen validation finalists.

The synchronous service is independent of HTTP. Optuna selects parameters; the existing
symbolic beam miner proposes conditions; every economic score comes from run_backtest.
Campaign JSON and the complete miner audit remain readable after a process restart.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import optuna

from pmx import ENGINE_VERSION
from pmx.agents.registry import ScriptedAgent, ScriptedGenome, make_agent
from pmx.engine.calendar import Calendar
from pmx.engine.liquidity import make_liquidity
from pmx.engine.runner import run_backtest
from pmx.journal import EquityMarked, Filled, canonical_sha256, read_journal
from pmx.metrics.projection import RunHandle
from pmx.optimizer.features import FEATURE_VERSION, FEATURES, HISTORY_BARS, MAX_FIT_ROWS_PER_MARKET, training_table
from pmx.optimizer.strategies import DiscoveryAgent, DiscoveryGenome, RuleAgent, RuleGenome
from pmx.rng import RngTree
from pmx.rules.miner import MinedCandidate, mine
from pmx.rules.rule import RULE_MIN_MARKETS, RULE_MIN_SUPPORT_DEFAULT, Rule, RuleClaim, RuleScope
from pmx.rules.tester import FoldPair
from pmx.types import Dataset, MarketMeta, RunConfig, interval_ms, market_set_hash

DISCOVERY_VERSION = "discovery.v2"
OBJECTIVE = "mean_return_bp - half_max_drawdown_bp - quarter_return_range_bp"
MIN_TRADED_MARKETS = 5
MAX_DRAWDOWN_BP = 2500
Json = dict[str, Any]
OnRun = Callable[[RunHandle, Dataset, RunConfig, Json], None]


@dataclass(frozen=True, slots=True)
class DiscoveryConfig:
    provider: str
    seed: int = 1
    n_trials: int = 30
    max_markets: int = 60
    bankroll_cents: int = 100_000
    n_splits: int = 3
    finalists: int = 3
    mining_budget: int = 500

    def __post_init__(self) -> None:
        bounds = {
            "seed": (0, 2**32 - 1), "n_trials": (1, 100), "max_markets": (5, 200),
            "bankroll_cents": (1000, 100_000_000), "n_splits": (2, 5),
            "finalists": (1, 5), "mining_budget": (100, 1000),
        }
        for name, (lo, hi) in bounds.items():
            value = getattr(self, name)
            if type(value) is not int or not lo <= value <= hi:
                raise ValueError(f"{name} must be an integer in {lo}..{hi}")
        if not isinstance(self.provider, str) or not self.provider:
            raise ValueError("provider is required")


@dataclass(frozen=True, slots=True)
class Period:
    name: str
    fold: str
    t0_ms: int
    t1_ms: int
    market_ids: tuple[str, ...]

    def to_dict(self) -> Json:
        return {**asdict(self), "market_ids": list(self.market_ids)}


def campaign_id_for(dataset: Dataset, config: DiscoveryConfig) -> str:
    return "c-" + canonical_sha256({
        "dataset_hash": dataset.manifest.dataset_hash, "engine_version": ENGINE_VERSION,
        "discovery_version": DISCOVERY_VERSION, "feature_version": FEATURE_VERSION,
        "optuna_version": optuna.__version__, "config": asdict(config),
    })[:24]


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_campaign(path: Path) -> Json:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Campaign artifact must be a JSON object")
    return value


def _sample(dataset: Dataset, config: DiscoveryConfig, fold: str) -> tuple[MarketMeta, ...]:
    eligible = [
        meta for meta in dataset.metas
        if meta.kind == "binary" and meta.provider == config.provider and meta.fold == fold
    ]
    eligible.sort(key=lambda meta: canonical_sha256({"seed": config.seed, "market_id": meta.id}))
    return tuple(sorted(eligible[:config.max_markets], key=lambda meta: meta.id))


def plan_periods(dataset: Dataset, config: DiscoveryConfig) -> tuple[Period, ...]:
    """Predeclare grid-aligned, disjoint periods using metadata only, never price/outcome values.

    The first 40% of sampled training resolution groups defines the proposal prefix.
    All later training time is split into equally long evaluation periods. A validation
    market listed earlier still cannot be traded before the manifest's training boundary.
    """
    train = _sample(dataset, config, "train")
    validation = _sample(dataset, config, "validation")
    if not train or not validation:
        raise ValueError("Discovery requires training and validation markets for this provider")
    span = interval_ms(dataset.manifest.interval_min)
    end = dataset.manifest.split.train_end_ms
    validation_end = dataset.manifest.split.validation_end_ms
    if end % span or validation_end % span:
        raise ValueError("Discovery fold boundaries must align with the dataset bar grid")
    group_ends: dict[str, int] = {}
    for meta in train:
        key = meta.event_key or meta.id
        group_ends[key] = max(group_ends.get(key, 0), meta.resolved_at_ms)
    ordered = sorted(group_ends.values())
    fit_end = (ordered[max(0, len(ordered) * 2 // 5 - 1)] // span + 1) * span
    start = max(dataset.manifest.window.start_ms // span * span, min(m.created_at_ms for m in train) // span * span)
    bars_left = (end - fit_end) // span
    if fit_end <= start or bars_left < 2 * config.n_splits:
        raise ValueError("Insufficient chronological training coverage for the requested time splits")
    periods = [Period("fit", "train", start, fit_end, tuple(meta.id for meta in train))]
    for index in range(config.n_splits):
        t0 = fit_end + (bars_left * index // config.n_splits) * span
        t1 = fit_end + (bars_left * (index + 1) // config.n_splits) * span
        ids = tuple(meta.id for meta in train if meta.created_at_ms < t1 and meta.resolved_at_ms >= t0)
        if not ids:
            raise ValueError(f"Training evaluation period {index + 1} has no markets; reduce time splits")
        periods.append(Period(f"train_{index + 1}", "train", t0, t1, ids))
    ids = tuple(meta.id for meta in validation if meta.created_at_ms < validation_end and meta.resolved_at_ms >= end)
    if not ids or validation_end <= end:
        raise ValueError("No later validation period is available")
    periods.append(Period("validation", "validation", end, validation_end, ids))
    return tuple(periods)


def _mine_rules(dataset: Dataset, config: DiscoveryConfig, fit: Period, directory: Path) -> tuple[list[Rule], Json]:
    wanted = set(fit.market_ids)
    table = training_table(
        dataset, [meta for meta in dataset.metas if meta.id in wanted],
        provider=config.provider, fit_t1_ms=fit.t1_ms,
    )
    audit = directory / "mining-candidates.jsonl"
    details: Json = {
        "status": "completed", "fit_t1_ms": fit.t1_ms, "features": list(FEATURES),
        "n_fit_markets": len(table.markets), "n_enumerated": 0, "n_accepted": 0,
        "n_fit_rows": sum(len(market.bars) for market in table.markets),
        "max_fit_rows_per_market": MAX_FIT_ROWS_PER_MARKET,
        "n_rules_used": 0, "budget": config.mining_budget, "audit_file": str(audit),
        "limitations": [
            "Fit-only symbolic proposals; no statistical promotion or certification.",
            "At most 256 observed-volume rows per market, uniformly sampled within the eligible fit prefix.",
        ],
    }
    directory.mkdir(parents=True, exist_ok=True)
    candidates: list[MinedCandidate] = []
    with audit.open("w", encoding="utf-8") as stream:
        def record(candidate: MinedCandidate) -> None:
            reasons = []
            if candidate.support < RULE_MIN_SUPPORT_DEFAULT:
                reasons.append("support_below_30")
            if candidate.n_markets < RULE_MIN_MARKETS:
                reasons.append("fewer_than_5_markets")
            if candidate.lift_bp <= 0:
                reasons.append("nonpositive_fit_lift")
            stream.write(json.dumps({
                "rule": candidate.rule.to_dict(), "lift_bp": candidate.lift_bp,
                "support": candidate.support, "n_markets": candidate.n_markets,
                "status": "rejected" if reasons else "accepted", "rejection_reasons": reasons,
            }, sort_keys=True) + "\n")

        if len(table.markets) < RULE_MIN_MARKETS:
            details["status"] = "insufficient_support"
            details["limitations"].append("Fewer than five resolved training markets before the fit cutoff.")
        else:
            pair = FoldPair("train", "train", tuple(m.meta.id for m in table.markets), (), fit.t1_ms, fit.t1_ms)
            for direction in (-1, 1):
                result = mine(
                    table, pair, scope=RuleScope(providers=(config.provider,), kinds=("binary",)),
                    claim=RuleClaim("bias", direction, 100, 0), horizon_bars=0,
                    features=FEATURES, min_support=RULE_MIN_SUPPORT_DEFAULT, beam=8,
                    candidates_max=config.mining_budget // 2, on_candidate=record,
                )
                details["n_enumerated"] += result.n_candidates
                candidates.extend(result.candidates)
            details["n_accepted"] = len(candidates)
            if not candidates:
                details["status"] = "no_supported_rules"
    # Preserve direction and structural diversity in the execution pool. At least half are
    # conjunctions when the miner found them; these are newly discovered conditions, not templates.
    ranked = sorted(candidates, key=lambda item: (len(item.rule.condition) == 1, item.order_key, item.rule.rule_id))
    # The directional quota must not let a large negative pool crowd out every positive rule.
    selected = [item.rule for item in ranked if item.rule.claim.direction == -1][:8] + [
        item.rule for item in ranked if item.rule.claim.direction == 1
    ][:8]
    details["n_rules_used"] = len(selected)
    return selected, details


def _genome(trial: optuna.Trial, rules: Sequence[Rule], fit_at: int) -> tuple[ScriptedGenome, str]:
    families = ["trend", "revert", "level"] + (["rule"] if rules else [])
    family = trial.suggest_categorical("family", families)
    max_edge = trial.suggest_int("max_edge_bp", 100, 2000, step=100)
    params = {
        "max_edge_bp": max_edge,
        "edge_min_bp": trial.suggest_int("edge_min_bp", 0, min(500, max_edge), step=50),
        "max_position": trial.suggest_int("max_position", 5, 50, step=5),
    }
    if family == "rule":
        rule = rules[trial.suggest_int("rule_index", 0, len(rules) - 1)]
        genome = RuleGenome(family, tuple(sorted(params.items())), rule, fit_at)
        condition = " AND ".join(f"{p.feature} {p.op} {p.value}" for p in rule.condition)
        side = "YES" if rule.claim.direction > 0 else "NO"
        return genome, (
            f"IF {condition}: shift belief {params['max_edge_bp']} bp toward {side} and target up to "
            f"{params['max_position']} contracts; otherwise flatten. Rebalance each decision bar."
        )
    params["strength_permille"] = trial.suggest_int("strength_permille", 250, 1500, step=250)
    if family == "level":
        params["anchor_bp"] = trial.suggest_int("anchor_bp", 1000, 9000, step=500)
        text = f"Shrink price toward a proposed anchor of {params['anchor_bp']} bp; bounded exposure."
    else:
        params["lookback_bars"] = trial.suggest_int("lookback_bars", 2, 30)
        verb = "Extend the past move" if family == "trend" else "Return toward the trailing mean"
        text = f"{verb} over {params['lookback_bars']} completed bars; bounded exposure."
    return DiscoveryGenome(family, tuple(sorted(params.items()))), text


def evaluate_candidate(
    dataset: Dataset, config: DiscoveryConfig, genome: ScriptedGenome, candidate_id: str,
    period: Period, runs_dir: Path, *, on_run: OnRun | None = None, candidate_info: Json | None = None,
) -> Json:
    """One fresh agent, cash account, RNG and liquidity model per candidate and period."""
    if not isinstance(genome, DiscoveryGenome):
        genome = DiscoveryGenome(genome.family, genome.genes)
    wanted = set(period.market_ids)
    view = replace(dataset, metas=tuple(meta for meta in dataset.metas if meta.id in wanted))
    if any(meta.fold == "sealed" or meta.provider != config.provider for meta in view.metas):
        raise ValueError("Evaluation may not mix providers or access sealed markets")
    run_config = RunConfig(
        seed=config.seed, interval_min=dataset.manifest.interval_min, t0_ms=period.t0_ms, t1_ms=period.t1_ms,
        bankroll_cents=config.bankroll_cents, fold=period.fold, amnesic=True, no_hive=True,
        news_per_market=0, news_global=0, bars_window=HISTORY_BARS, trades_window=0,
    )
    ids = Calendar(view, run_config).market_ids()
    if not ids:
        raise ValueError(f"Period {period.name} has no executable calendar")
    run_config = replace(run_config, market_ids_hash=market_set_hash(ids))
    agent: ScriptedAgent
    if isinstance(genome, RuleGenome):
        if period.t0_ms < genome.fitted_at_ms:
            raise ValueError("Rule evaluation starts before fit information became available")
        agent = RuleAgent(agent_id=candidate_id, genome=genome)
    else:
        checked = make_agent(candidate_id, genome)
        agent = DiscoveryAgent(agent_id=checked.agent_id, genome=checked.genome)
    handle = run_backtest(
        view, (agent,), run_config, tree=RngTree(config.seed), journal_dir=runs_dir,
        liquidity=make_liquidity(run_config),
    )
    row = handle.projection.agent(candidate_id)
    final_equity = config.bankroll_cents
    n_fills = 0
    traded_ids: set[str] = set()
    for event in read_journal(handle.journal_path, validate=False):
        if isinstance(event, EquityMarked):
            final_equity = event.equity_cents
        elif isinstance(event, Filled) and event.filled_size:
            n_fills += 1
            traded_ids.add(event.market_id)
    if on_run is not None:
        on_run(handle, view, run_config, candidate_info or {})
    # The runner's legacy projection PnL is final cash. A truncated calendar can still hold
    # inventory, so use its actual EquityMarked event (binary collateral accounting included).
    return {
        "period": period.name, "fold": period.fold, "t0_ms": period.t0_ms, "t1_ms": period.t1_ms,
        "market_ids": list(ids), "n_markets": len(ids), "run_id": handle.run_id,
        "run_dir": str(handle.run_dir), "journal_hash": handle.journal_hash,
        "pnl_cents": final_equity - config.bankroll_cents, "final_equity_cents": final_equity,
        "fees_cents": row.fees_paid_cents, "max_drawdown_bp": abs(row.max_drawdown_bp), "n_fills": n_fills,
        "traded_market_ids": sorted(traded_ids),
        "n_settled_markets": row.n_markets,
    }


def _objective(results: Sequence[Mapping[str, Any]], bankroll: int) -> float:
    returns = [int(row["pnl_cents"]) * 10_000 / bankroll for row in results]
    return sum(returns) / len(returns) - max(int(row["max_drawdown_bp"]) for row in results) / 2 - (
        max(returns) - min(returns)
    ) / 4


def run_campaign(
    dataset: Dataset, config: DiscoveryConfig, output_dir: Path, *, runs_dir: Path | None = None,
    on_run: OnRun | None = None, cancel_requested: Callable[[], bool] | None = None,
) -> Json:
    """Execute and persist a deterministic, bounded campaign, returning plain JSON.

    Completed artifacts are idempotently reused. Interrupted artifacts remain readable; a
    retry deterministically recomputes the same study instead of pretending a partial study
    completed. Selection is committed before validation is ever evaluated.
    """
    campaign_id = campaign_id_for(dataset, config)
    directory = output_dir / campaign_id
    path = directory / "campaign.json"
    if path.exists():
        saved = read_campaign(path)
        if saved.get("status") == "completed":
            return saved
        attempts = directory / "attempts"
        number = len(list(attempts.glob("*.json"))) + 1
        _write(attempts / f"attempt-{number:04d}.json", saved)
    state: Json = {
        "campaign_id": campaign_id, "status": "running", "dataset": dataset.manifest.name,
        "dataset_hash": dataset.manifest.dataset_hash, "currency": "", "config": asdict(config),
        "engine_version": ENGINE_VERSION, "discovery_version": DISCOVERY_VERSION,
        "objective_name": OBJECTIVE, "progress": {"completed_trials": 0, "total_trials": config.n_trials},
        "splits": [], "candidates": [], "selected_candidate_ids": [], "error": None,
        "baseline": {"name": "No-trade market follower", "pnl_cents": 0, "objective": 0},
        "selection_policy": {
            "min_traded_markets": MIN_TRADED_MARKETS, "require_trades_in_every_train_period": True,
            "max_drawdown_bp": MAX_DRAWDOWN_BP,
        },
        "limitations": [
            "Exploratory search: no profitability, statistical significance or certification claim.",
            "Known-resolved binary sample: conditional results that do not measure censored markets.",
            "Proposals use an initial training prefix; parameters use later internal training windows only.",
            "Validation is read only after finalists are frozen; sealed market tapes are never accessed.",
            "Each candidate and period starts with equal fresh capital and its own simulated liquidity.",
            "Window returns use engine marked equity; open inventory is not force-liquidated at window boundaries.",
            "Daily or coarse bars impose decision latency; historical volume is an execution approximation.",
            "Event dependence, unknown source chronology and repeated research require separate robustness work.",
            "Expiry and external information features are excluded; no execution-cost stress test in this campaign.",
            "The historical simulator clips fills to bar ranges; flat-price bars may understate effective spread.",
        ],
    }
    _write(path, state)
    try:
        if dataset.purpose != "research":
            raise ValueError("Discovery requires a research dataset, not showcase data")
        periods = plan_periods(dataset, config)
        state["splits"] = [period.to_dict() for period in periods]
        # First loaded record is a training market; validation is metadata-only until selection.
        state["currency"] = dataset.market(periods[0].market_ids[0]).currency
        rules, state["mining"] = _mine_rules(dataset, config, periods[0], directory)
        if not rules:
            state["limitations"].append(
                "No supported symbolic rules in the fit prefix; this campaign only searches predefined families."
            )
        _write(path, state)
        study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=config.seed))
        initial = (["rule"] if rules else []) + ["trend", "revert", "level"]
        for family in initial:
            study.enqueue_trial({"family": family})
        genomes: dict[str, ScriptedGenome] = {}
        run_root = directory / "runs" if runs_dir is None else runs_dir
        for _ in range(config.n_trials):
            if cancel_requested is not None and cancel_requested():
                state["status"] = "cancelled"
                _write(path, state)
                return state
            trial = study.ask()
            record: Json = {
                "candidate_id": f"trial_{trial.number}", "trial_number": trial.number, "family": "",
                "parameters": {}, "status": "running", "error": None, "objective": None,
                "train_results": [], "validation_results": [], "selected": False,
                "rule": None, "rule_text": "", "rejection_reasons": [],
            }
            state["candidates"].append(record)
            try:
                genome, text = _genome(trial, rules, periods[0].t1_ms)
                candidate_id = "strategy-" + canonical_sha256(genome.to_dict())[:8]
                genomes[candidate_id] = genome
                record.update(
                    candidate_id=candidate_id, family=genome.family, parameters=dict(genome.genes),
                    genome=genome.to_dict(), rule_text=text,
                    rule=genome.rule.to_dict() if isinstance(genome, RuleGenome) and genome.rule else None,
                )
                _write(path, state)
                for period in periods[1:-1]:
                    record["train_results"].append(evaluate_candidate(
                        dataset, config, genome, candidate_id, period, run_root,
                    ))
                    _write(path, state)
                results = record["train_results"]
                traded = {market_id for row in results for market_id in row["traded_market_ids"]}
                if any(row["n_fills"] == 0 for row in results):
                    record["rejection_reasons"].append("no_trades_in_at_least_one_train_period")
                if len(traded) < MIN_TRADED_MARKETS:
                    record["rejection_reasons"].append("fewer_than_5_distinct_traded_markets")
                if max(row["max_drawdown_bp"] for row in results) > MAX_DRAWDOWN_BP:
                    record["rejection_reasons"].append("drawdown_exceeds_25_percent")
                record["objective"] = _objective(results, config.bankroll_cents)
                record["status"] = "rejected" if record["rejection_reasons"] else "completed"
                study.tell(trial, record["objective"] if record["status"] == "completed" else -1e12)
            except Exception as error:
                record.update(status="failed", error=f"{type(error).__name__}: {error}")
                record["rejection_reasons"].append("evaluation_failed")
                study.tell(trial, state=optuna.trial.TrialState.FAIL)
            record["search_parameters"] = dict(trial.params)
            state["progress"]["completed_trials"] += 1
            _write(path, state)
        if all(row["status"] == "failed" for row in state["candidates"]):
            raise RuntimeError("All candidate evaluations failed; inspect the persisted candidate errors")
        eligible = sorted(
            (row for row in state["candidates"] if row["status"] == "completed"),
            key=lambda row: (-row["objective"], row["candidate_id"], row["trial_number"]),
        )
        for record in eligible:
            if record["candidate_id"] in state["selected_candidate_ids"]:
                continue
            record["selected"] = True
            state["selected_candidate_ids"].append(record["candidate_id"])
            if len(state["selected_candidate_ids"]) >= config.finalists:
                break
        state["status"] = "validating"
        _write(path, state)
        _write(directory / "selection.json", {
            "candidate_ids": state["selected_candidate_ids"], "objective_name": OBJECTIVE,
            "selection_source": "internal_train_only", "validation_t0_ms": periods[-1].t0_ms,
        })
        for record in state["candidates"]:
            if not record["selected"]:
                continue
            if cancel_requested is not None and cancel_requested():
                state["status"] = "cancelled"
                _write(path, state)
                return state
            try:
                record["validation_results"].append(evaluate_candidate(
                    dataset, config, genomes[record["candidate_id"]], record["candidate_id"], periods[-1], run_root,
                    on_run=on_run, candidate_info={**record, "campaign_id": campaign_id},
                ))
                record["validation_status"] = "completed"
            except Exception as error:
                record["validation_status"] = "failed"
                record["validation_error"] = f"{type(error).__name__}: {error}"
            _write(path, state)
        state["status"] = "completed"
        _write(path, state)
        return state
    except Exception as error:
        state.update(status="failed", error=f"{type(error).__name__}: {error}")
        _write(path, state)
        raise
