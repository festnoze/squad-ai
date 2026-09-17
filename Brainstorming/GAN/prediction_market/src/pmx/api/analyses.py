"""Event-driven campaign reviews; separate capacity, artifacts, failures and subscription usage."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from pmx.analysis.campaign import REPORT_VERSION, child, evidence_packet, fingerprint, read_object
from pmx.api.service import write_json
from pmx.llm.campaign_review import Review, review_markdown, review_with_codex

Json = dict[str, Any]
Reviewer = Callable[[Json, Path], Json]


class AnalysisService:
    def __init__(self, dataset_root: Path, runs_root: Path, *, reviewer: Reviewer = review_with_codex) -> None:
        self.dataset_root = dataset_root
        self.runs_root = runs_root
        self.root = runs_root / "analyses"
        self.settings_path = self.root / "settings.json"
        self.reviewer = reviewer
        self.lock = RLock()
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pmx-analysis")

    def settings(self) -> Json:
        with self.lock:
            if self.settings_path.exists():
                return read_object(self.settings_path)
            return {"enabled": False, "enabled_at": None, "provider": "codex-chatgpt-subscription"}

    def configure(self, *, enabled: bool) -> Json:
        with self.lock:
            settings = self.settings()
            if enabled and not settings["enabled"]:
                settings["enabled_at"] = datetime.now(UTC).isoformat()
            settings["enabled"] = enabled
            write_json(self.settings_path, settings)
            return settings

    def _campaign(self, campaign_id: str) -> Json:
        return read_object(child(self.runs_root / "campaigns", campaign_id) / "campaign.json")

    def detail(self, campaign_id: str) -> Json:
        with self.lock:
            return self._detail(campaign_id)

    def _detail(self, campaign_id: str) -> Json:
        root = child(self.root, campaign_id)
        state_path = root / "state.json"
        state: Json = read_object(state_path) if state_path.exists() else {
            "campaign_id": campaign_id, "status": "not_requested", "error": None,
        }
        state["automatic_enabled"] = self.settings()["enabled"]
        state["report"] = None
        if state["status"] == "completed":
            state["report"] = read_object(child(root, state["attempt_id"]) / "review.json")
        return state

    def enqueue_auto(self, campaign: Json) -> None:
        # Publishing a review can never make a successful backtest fail.
        if campaign.get("status") != "completed":
            return
        try:
            if self.settings()["enabled"]:
                self.submit(campaign["campaign_id"])
        except Exception as error:
            directory = child(self.root, campaign["campaign_id"])
            with self.lock:
                write_json(directory / "state.json", {
                    "campaign_id": campaign["campaign_id"], "status": "failed",
                    "error": f"Préparation de l'analyse : {type(error).__name__}: {error}",
                })

    def submit(self, campaign_id: str, *, retry: bool = False) -> Json:
        campaign = self._campaign(campaign_id)
        if campaign["status"] != "completed":
            raise ValueError("Attendez la fin complète de la campagne pour demander son analyse.")
        key = fingerprint({"version": REPORT_VERSION, "campaign": campaign})
        with self.lock:
            current = self.detail(campaign_id)
            if current["status"] in ("queued", "running"):
                return current
            if current.get("request_hash") == key and (
                current["status"] == "completed" or (current["status"] == "failed" and not retry)
            ):
                return current
            attempt_id = "a-" + uuid4().hex
            directory = child(self.root, campaign_id)
            state = {
                "campaign_id": campaign_id, "status": "queued", "request_hash": key,
                "attempt_id": attempt_id, "version": REPORT_VERSION,
                "created_at": datetime.now(UTC).isoformat(), "error": None,
                "provider": "codex-chatgpt-subscription",
            }
            write_json(directory / "state.json", state)
            self.worker.submit(self._work, campaign, state)
            return self.detail(campaign_id)

    def _work(self, campaign: Json, state: Json) -> None:
        directory = child(self.root, campaign["campaign_id"])
        attempt = child(directory, state["attempt_id"])
        try:
            attempt.mkdir(parents=True, exist_ok=True)
            with self.lock:
                state["status"] = "running"
                write_json(directory / "state.json", state)
            packet = evidence_packet(campaign, run_root=self.runs_root, dataset_root=self.dataset_root)
            state["evidence_hash"] = fingerprint(packet)
            write_json(attempt / "evidence.json", packet)
            report = Review.model_validate(self.reviewer(packet, attempt)).model_dump()
            write_json(attempt / "review.json", report)
            (attempt / "review.md").write_text(review_markdown(report, campaign["campaign_id"]), encoding="utf-8")
            state["status"] = "completed"
        except Exception as error:
            state.update(status="failed", error=f"{type(error).__name__}: {error}")
        state["finished_at"] = datetime.now(UTC).isoformat()
        # A result from an older interrupted attempt cannot overwrite a later explicit retry.
        with self.lock:
            if read_object(directory / "state.json").get("attempt_id") == state["attempt_id"]:
                write_json(directory / "state.json", state)

    def recover(self) -> None:
        with self.lock:
            self._recover()

    def _recover(self) -> None:
        settings = self.settings()
        for state_path in self.root.glob("c-*/state.json"):
            state = read_object(state_path)
            if state["status"] == "running":
                state.update(
                    status="failed", error="Analyse interrompue au redémarrage. Relance manuelle disponible."
                )
                write_json(state_path, state)
            elif state["status"] == "queued":
                self.worker.submit(self._work, self._campaign(state["campaign_id"]), state)
        if settings["enabled"] and settings.get("enabled_at"):
            since = datetime.fromisoformat(settings["enabled_at"]).timestamp()
            for path in (self.runs_root / "campaigns").glob("c-*/campaign.json"):
                if path.stat().st_mtime >= since:
                    self.enqueue_auto(read_object(path))

    def export(self, campaign_id: str, *, evidence: bool = False) -> Path:
        state = self.detail(campaign_id)
        if not state.get("attempt_id"):
            raise KeyError("Aucune analyse enregistrée.")
        directory = child(child(self.root, campaign_id), state["attempt_id"])
        path = directory / ("evidence.json" if evidence else "review.md")
        if not path.exists():
            raise KeyError("L'artefact n'est pas encore disponible.")
        return path

    def close(self) -> None:
        self.worker.shutdown(wait=True)
