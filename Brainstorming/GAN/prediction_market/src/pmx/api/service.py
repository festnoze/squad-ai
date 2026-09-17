"""One bounded background worker, persisted jobs and views derived from the v2 journal."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from pmx import ENGINE_VERSION
from pmx.agents.registry import DEFAULT_ROSTER, NAMES, make_agent
from pmx.api.catalogue import LIMITATIONS, Catalogue, market_summary, valid_identifier
from pmx.api.models import RunRequest
from pmx.engine.calendar import Calendar
from pmx.engine.liquidity import make_liquidity
from pmx.engine.runner import run_backtest
from pmx.journal import (
    BarClosed,
    EquityMarked,
    FeeCharged,
    Filled,
    ForecastRecorded,
    MarketPriced,
    SettlementApplied,
    canonical_sha256,
    read_journal,
)
from pmx.metrics.projection import RunHandle
from pmx.rng import RngTree
from pmx.scoring import signed_mean
from pmx.types import Dataset, RunConfig, market_set_hash


def write_json(path: Path, payload: object) -> None:
    """Replace only after a full write, keeping readers away from partially written JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Le résultat sauvegardé n'est pas un objet JSON.")
    return payload


def select_dataset(dataset: Dataset, request: RunRequest) -> tuple[Dataset, RunConfig]:
    """Select independently of outcomes, and delegate the actual tradable set to Calendar.

    The metadata view shares the verified loader/cache without copying or resealing the dataset.
    A seed-keyed digest over IDs makes selection independent of input enumeration order.
    """
    eligible = [
        meta
        for meta in dataset.metas
        if meta.provider == request.provider and meta.fold == request.fold and meta.kind == "binary"
    ]
    eligible.sort(key=lambda meta: canonical_sha256({"seed": request.seed, "market_id": meta.id}))
    selected = tuple(sorted(eligible[: request.max_markets], key=lambda meta: meta.id))
    if not selected:
        raise ValueError("Aucun marché disponible pour ce fournisseur et cette partition.")
    view = replace(dataset, metas=selected)
    config = RunConfig(
        seed=request.seed,
        interval_min=dataset.manifest.interval_min,
        bankroll_cents=request.bankroll_cents,
        fold=request.fold,
        amnesic=True,
        no_hive=True,
    )
    ids = Calendar(view, config).market_ids()
    if not ids:
        raise ValueError("La sélection ne contient aucune barre exécutable.")
    return view, replace(config, market_ids_hash=market_set_hash(ids))


def journal_views(handle: RunHandle, bankroll: int) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Read the recorded prices/forecasts/positions/equity; never simulate fills a second time."""
    # This process just wrote and validated the journal through run_backtest. The journal reader
    # explicitly supports this path; a later independent replay still validates every event.
    events = read_journal(handle.journal_path, validate=False)
    agent_ids = [row.agent_id for row in handle.projection.agents]
    market_ids = [row.market_id for row in handle.projection.markets]
    replays: dict[str, dict[str, Any]] = {
        market_id: {"market_id": market_id, "agent_ids": agent_ids, "ticks": [], "fills": []}
        for market_id in market_ids
    }
    equities = dict.fromkeys(agent_ids, bankroll)
    positions: dict[tuple[str, str], int] = {}
    probabilities: dict[tuple[str, str], int] = {}
    prices: dict[str, int] = {}
    equity_points: list[dict[str, Any]] = []
    fills_by_order: dict[tuple[int, str], dict[str, Any]] = {}
    for event in events:
        if isinstance(event, MarketPriced):
            prices[event.market_id] = event.last_close_bp
        elif isinstance(event, ForecastRecorded):
            probabilities[event.agent_id, event.market_id] = event.prob_ppm
        elif isinstance(event, Filled):
            positions[event.agent_id, event.market_id] = event.position_after
            fill: dict[str, Any] = {
                "t_ms": event.bar_ms,
                "agent_id": event.agent_id,
                "side": event.side,
                "size": event.filled_size,
                "price_bp": event.fill_price_bp,
                "fee_cents": 0,
            }
            if event.market_id in replays and event.filled_size:
                replays[event.market_id]["fills"].append(fill)
                fills_by_order[event.bar_ms, event.order_id] = fill
        elif isinstance(event, FeeCharged):
            fill = fills_by_order.get((event.bar_ms, event.order_id), {})
            if fill:
                fill["fee_cents"] += event.fee_cents
        elif isinstance(event, SettlementApplied):
            positions[event.agent_id, event.market_id] = 0
        elif isinstance(event, EquityMarked):
            equities[event.agent_id] = event.equity_cents
        elif isinstance(event, BarClosed):
            equity_points.append({"t_ms": event.bar_ms, "agents": dict(equities)})
            for market_id, price in sorted(prices.items()):
                if market_id not in replays:
                    continue
                replays[market_id]["ticks"].append(
                    {
                        "t_ms": event.bar_ms,
                        "price_bp": price,
                        "agents": {
                            agent_id: {
                                "prob_ppm": probabilities.get((agent_id, market_id), price * 100),
                                "position": positions.get((agent_id, market_id), 0),
                                "equity_cents": equities[agent_id],
                            }
                            for agent_id in agent_ids
                        },
                    }
                )
            prices.clear()
    return equity_points, replays


def execute_run(dataset: Dataset, request: RunRequest, runs_dir: Path) -> dict[str, Any]:
    """The synchronous CLI and the HTTP worker share this one engine entry point."""
    view, config = select_dataset(dataset, request)
    request_key = canonical_sha256(
        {
            "dataset_hash": dataset.manifest.dataset_hash,
            "engine_version": ENGINE_VERSION,
            "genomes": {
                agent_id: genome.to_dict() for agent_id, genome in DEFAULT_ROSTER if agent_id in request.agent_ids
            },
            **request.model_dump(),
        }
    )
    for path in runs_dir.glob("r-*/mvp-detail.json"):
        metadata_path = path.parent / "mvp-request.json"
        if metadata_path.exists() and read_json(metadata_path).get("request_key") == request_key:
            return read_json(path)
    handle = run_backtest(
        view,
        tuple(make_agent(agent_id) for agent_id in request.agent_ids),
        config,
        tree=RngTree(config.seed),
        journal_dir=runs_dir,
        liquidity=make_liquidity(config),
    )
    equity, replays = journal_views(handle, request.bankroll_cents)
    actual_ids = Calendar(view, config).market_ids()
    markets = [market_summary(view, view.meta(market_id)) for market_id in actual_ids]
    limitations = [
        *LIMITATIONS,
        "Les stratégies partagent la liquidité simulée ; changer le groupe peut changer les exécutions.",
        "Échantillon borné, déterministe et exploratoire ; les scores ne sont pas des garanties.",
    ]
    run = {
        "run_id": handle.run_id,
        "dataset": dataset.manifest.name,
        "dataset_hash": handle.dataset_hash,
        "provider": request.provider,
        "currency": markets[0]["currency"],
        "fold": request.fold,
        "seed": request.seed,
        "bankroll_cents": request.bankroll_cents,
        "market_ids": list(actual_ids),
        "agent_ids": [row.agent_id for row in handle.projection.agents],
        "n_markets": len(actual_ids),
        "journal_hash": handle.journal_hash,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "completed",
        "limitations": limitations,
    }
    leaderboard = []
    for row in handle.projection.agents:
        cells = handle.projection.rows_of(row.agent_id)
        leaderboard.append(
            {
                "agent_id": row.agent_id,
                "name": NAMES[row.agent_id],
                "baseline": row.agent_id == "follower",
                "n_markets": row.n_markets,
                "mean_brier_micro": signed_mean([cell.agent_brier_tw_micro for cell in cells]),
                "market_brier_micro": signed_mean([cell.market_brier_tw_micro for cell in cells]),
                "skill_micro": row.skill.point,
                "pnl_cents": row.pnl_cents,
                "fees_cents": row.fees_paid_cents,
                "n_fills": sum(
                    1 for replay in replays.values() for fill in replay["fills"] if fill["agent_id"] == row.agent_id
                ),
                "max_drawdown_bp": row.max_drawdown_bp,
                "final_equity_cents": equity[-1]["agents"][row.agent_id] if equity else request.bankroll_cents,
            }
        )
    detail = {"run": run, "leaderboard": leaderboard, "equity": equity, "markets": markets}
    for market_id, payload in replays.items():
        write_json(handle.run_dir / "mvp-replay" / f"{canonical_sha256(market_id)}.json", payload)
    write_json(handle.run_dir / "mvp-request.json", {"request_key": request_key, "request": request.model_dump()})
    write_json(handle.run_dir / "mvp-detail.json", detail)
    return detail


class RunService:
    """Persistent lifecycle state is kept outside deterministic engine artifacts.

    Atomic JSON files require no database connection shared between the server and worker threads.
    Capacity is one pending or running run; excess work is explicitly refused.
    """

    def __init__(self, catalogue: Catalogue, runs_dir: Path) -> None:
        self.catalogue = catalogue
        self.runs_dir = runs_dir.resolve()
        self.jobs_dir = self.runs_dir / "mvp-jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pmx-mvp")
        for path in self.jobs_dir.glob("*.json"):
            job = read_json(path)
            if job.get("status") in ("queued", "running"):
                job.update(status="failed", error="Simulation interrompue lors de l'arrêt précédent. Relancez-la.")
                write_json(path, job)

    def close(self) -> None:
        self.worker.shutdown(wait=True)

    def get_job(self, job_id: str) -> dict[str, Any]:
        if not valid_identifier(job_id):
            raise KeyError("Identifiant de tâche invalide.")
        path = self.jobs_dir / f"{job_id}.json"
        with self.lock:
            if not path.is_file():
                raise KeyError("Tâche introuvable.")
            return read_json(path)

    def submit(self, request: RunRequest) -> dict[str, Any]:
        dataset = self.catalogue.load(request.dataset)
        select_dataset(dataset, request)
        with self.lock:
            if any(read_json(path)["status"] in ("queued", "running") for path in self.jobs_dir.glob("*.json")):
                raise RuntimeError("Une simulation est déjà en cours. Attendez sa fin avant de relancer.")
            job = {"job_id": "j-" + uuid4().hex, "status": "queued", "run_id": None, "error": None}
            write_json(self.jobs_dir / f"{job['job_id']}.json", job)
            self.worker.submit(self._work, str(job["job_id"]), dataset, request)
            return dict(job)

    def _work(self, job_id: str, dataset: Dataset, request: RunRequest) -> None:
        path = self.jobs_dir / f"{job_id}.json"
        with self.lock:
            job = self.get_job(job_id)
            job["status"] = "running"
            write_json(path, job)
        try:
            detail = execute_run(dataset, request, self.runs_dir)
        except Exception as error:
            job.update(status="failed", error=f"{type(error).__name__}: {error}")
        else:
            job.update(status="completed", run_id=detail["run"]["run_id"])
        with self.lock:
            write_json(path, job)

    def history(self) -> list[dict[str, Any]]:
        rows = [read_json(path)["run"] for path in self.runs_dir.glob("r-*/mvp-detail.json")]
        return sorted(rows, key=lambda row: str(row["created_at"]), reverse=True)

    def detail(self, run_id: str) -> dict[str, Any]:
        if not valid_identifier(run_id):
            raise KeyError("Identifiant de simulation invalide.")
        path = self.runs_dir / run_id / "mvp-detail.json"
        if not path.is_file():
            raise KeyError("Simulation introuvable ou encore incomplète.")
        return read_json(path)

    def market_replay(self, run_id: str, market_id: str) -> dict[str, Any]:
        detail = self.detail(run_id)
        if market_id not in detail["run"]["market_ids"]:
            raise KeyError("Ce marché ne fait pas partie de cette simulation.")
        return read_json(self.runs_dir / run_id / "mvp-replay" / f"{canonical_sha256(market_id)}.json")
