"""Campaign lifecycle using the same local worker and recorded execution views as ordinary runs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pmx.api.catalogue import market_summary, valid_identifier
from pmx.api.models import CampaignRequest
from pmx.api.service import RunService, journal_views, read_json, write_json
from pmx.engine.calendar import Calendar
from pmx.journal import canonical_sha256
from pmx.metrics.projection import RunHandle
from pmx.optimizer.discovery import DiscoveryConfig, campaign_id_for, run_campaign
from pmx.scoring import signed_mean
from pmx.types import Dataset, RunConfig


def campaign_config(request: CampaignRequest) -> DiscoveryConfig:
    return DiscoveryConfig(**request.model_dump(exclude={"dataset"}))


def persist_campaign_run(
    handle: RunHandle, dataset: Dataset, config: RunConfig, info: dict[str, Any]
) -> None:
    """Publish a finalist's real journal through the existing result/replay routes."""
    equity, replays = journal_views(handle, config.bankroll_cents)
    ids = Calendar(dataset, config).market_ids()
    markets = [market_summary(dataset, dataset.meta(market_id)) for market_id in ids]
    if not markets:
        raise ValueError("Le finaliste n'a aucun marché rejouable.")
    name = str(info.get("name") or info.get("family") or info.get("candidate_id", "Candidat"))
    leaderboard = []
    for agent in handle.projection.agents:
        cells = handle.projection.rows_of(agent.agent_id)
        leaderboard.append({
            "agent_id": agent.agent_id, "name": name, "baseline": False,
            "n_markets": agent.n_markets,
            "mean_brier_micro": signed_mean([cell.agent_brier_tw_micro for cell in cells]),
            "market_brier_micro": signed_mean([cell.market_brier_tw_micro for cell in cells]),
            "skill_micro": agent.skill.point,
            "pnl_cents": (equity[-1]["agents"][agent.agent_id] - config.bankroll_cents if equity else 0),
            "fees_cents": agent.fees_paid_cents,
            "n_fills": sum(1 for replay in replays.values() for fill in replay["fills"]
                           if fill["agent_id"] == agent.agent_id),
            "max_drawdown_bp": agent.max_drawdown_bp,
            "final_equity_cents": (equity[-1]["agents"][agent.agent_id]
                                   if equity else config.bankroll_cents),
        })
    run = {
        "run_id": handle.run_id, "dataset": dataset.manifest.name,
        "dataset_hash": handle.dataset_hash, "provider": markets[0]["provider"],
        "currency": markets[0]["currency"], "fold": config.fold, "seed": config.seed,
        "bankroll_cents": config.bankroll_cents, "market_ids": list(ids),
        "agent_ids": [row.agent_id for row in handle.projection.agents],
        "n_markets": len(ids), "journal_hash": handle.journal_hash,
        "created_at": datetime.now(UTC).isoformat(), "status": "completed",
        "campaign_id": info.get("campaign_id"), "candidate_id": info.get("candidate_id"),
        "limitations": [
            "Finaliste évalué seul, après sélection sur les fenêtres d'entraînement.",
            "Validation exploratoire ; aucune certification de rentabilité.",
            "Prix et liquidité simulés ; le replay restitue les événements du moteur.",
        ],
    }
    for market_id, replay in replays.items():
        write_json(handle.run_dir / "mvp-replay" / f"{canonical_sha256(market_id)}.json", replay)
    write_json(handle.run_dir / "mvp-detail.json", {
        "run": run, "leaderboard": leaderboard, "equity": equity, "markets": markets,
    })


class CampaignService:
    """Persisted asynchronous campaigns sharing the run service's single worker and capacity lock."""

    def __init__(self, runs: RunService, *, on_completed: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.runs = runs
        self.on_completed = on_completed
        self.root = runs.runs_dir / "campaigns"
        self.root.mkdir(parents=True, exist_ok=True)
        # RunService already marks jobs interrupted by an actual application restart as failed.
        for path in runs.jobs_dir.glob("*.json"):
            job = read_json(path)
            if job.get("kind") == "campaign" and job.get("status") == "failed":
                campaign_id = job.get("campaign_id")
                if isinstance(campaign_id, str) and valid_identifier(campaign_id):
                    record = self.root / campaign_id / "campaign.json"
                    if record.is_file():
                        campaign = read_json(record)
                        if campaign.get("status") in ("queued", "running", "validating"):
                            campaign.update(status="failed", error=job.get("error"))
                            write_json(record, campaign)

    def submit(self, request: CampaignRequest) -> dict[str, Any]:
        dataset = self.runs.catalogue.load(request.dataset)
        config = campaign_config(request)
        campaign_id = campaign_id_for(dataset, config)
        with self.runs.lock:
            if any(read_json(path)["status"] in ("queued", "running")
                   for path in self.runs.jobs_dir.glob("*.json")):
                raise RuntimeError("Un calcul est déjà en cours. Attendez sa fin ou annulez la campagne.")
            existing = self.root / campaign_id / "campaign.json"
            cached = existing.is_file() and read_json(existing).get("status") == "completed"
            if not existing.is_file():
                providers = [
                    meta for meta in dataset.metas if meta.provider == request.provider and meta.fold == "train"
                ]
                if not providers:
                    raise ValueError("Aucun marché d'entraînement disponible pour ce fournisseur.")
                write_json(existing, {
                    "campaign_id": campaign_id, "status": "queued", "dataset": request.dataset,
                    "dataset_hash": dataset.manifest.dataset_hash,
                    "currency": dataset.market(providers[0].id).currency,
                    "config": request.model_dump(exclude={"dataset"}),
                    "progress": {"completed_trials": 0, "total_trials": request.n_trials},
                    "candidates": [], "splits": [], "selected_candidate_ids": [],
                    "mining": None, "limitations": [], "error": None,
                })
            job = {
                "job_id": "j-" + uuid4().hex, "kind": "campaign",
                "status": "completed" if cached else "queued", "run_id": None,
                "campaign_id": campaign_id, "error": None, "cancel_requested": False,
                "created_at": datetime.now(UTC).isoformat(), "request": request.model_dump(),
            }
            write_json(self.runs.jobs_dir / f"{job['job_id']}.json", job)
            if not cached:
                self.runs.worker.submit(self._work, str(job["job_id"]), dataset, config)
            return job

    def _cancelled(self, job_id: str) -> bool:
        return bool(self.runs.get_job(job_id).get("cancel_requested"))

    def _work(self, job_id: str, dataset: Dataset, config: DiscoveryConfig) -> None:
        path = self.runs.jobs_dir / f"{job_id}.json"
        with self.runs.lock:
            job = self.runs.get_job(job_id)
            job["status"] = "running"
            write_json(path, job)
        try:
            campaign = run_campaign(
                dataset, config, output_dir=self.root, runs_dir=self.runs.runs_dir,
                on_run=persist_campaign_run, cancel_requested=lambda: self._cancelled(job_id),
            )
        except Exception as error:
            job.update(status="failed", error=f"{type(error).__name__}: {error}")
            record = self.root / str(job["campaign_id"]) / "campaign.json"
            if record.is_file():
                interrupted = read_json(record)
                interrupted.update(status="failed", error=job["error"])
                write_json(record, interrupted)
        else:
            job.update(status=campaign["status"], error=campaign.get("error"))
        with self.runs.lock:
            job["cancel_requested"] = self.runs.get_job(job_id).get("cancel_requested", False)
            write_json(path, job)
        if job["status"] == "completed" and self.on_completed is not None:
            self.on_completed(self.detail(str(job["campaign_id"])))

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self.runs.lock:
            job = self.runs.get_job(job_id)
            if job.get("kind") != "campaign":
                raise ValueError("Seules les campagnes acceptent l'annulation entre deux évaluations.")
            if job["status"] in ("queued", "running"):
                job["cancel_requested"] = True
                write_json(self.runs.jobs_dir / f"{job_id}.json", job)
            return job

    def detail(self, campaign_id: str) -> dict[str, Any]:
        if not valid_identifier(campaign_id):
            raise KeyError("Identifiant de campagne invalide.")
        path = self.root / campaign_id / "campaign.json"
        if not path.is_file():
            raise KeyError("Campagne en attente de démarrage ou introuvable.")
        return read_json(path)

    def history(self) -> list[dict[str, Any]]:
        rows = []
        for path in self.root.glob("c-*/campaign.json"):
            detail = read_json(path)
            summary = {key: value for key, value in detail.items() if key not in ("candidates", "splits")}
            summary["created_at"] = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
            rows.append(summary)
        return sorted(rows, key=lambda row: str(row["created_at"]), reverse=True)
