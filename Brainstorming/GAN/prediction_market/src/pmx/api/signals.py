"""Persistent, bounded application jobs for the fixed R1 signal protocol."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

from pmx.analysis.campaign import child, fingerprint, read_object
from pmx.analysis.signals import PROTOCOL, protected_ids, study
from pmx.api.catalogue import Catalogue
from pmx.api.service import write_json


class SignalService:
    def __init__(self, catalogue: Catalogue, runs_root: Path) -> None:
        self.catalogue = catalogue
        self.root = runs_root / "signal-studies"
        self.lock = RLock()
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pmx-signals")
        for path in self.root.glob("s-*/state.json"):
            state = read_object(path)
            if state["status"] in ("queued", "running"):
                state.update(status="failed", error="Étude interrompue ; relance explicite disponible.")
                write_json(path, state)

    def history(self) -> list[dict[str, Any]]:
        with self.lock:
            return sorted(
                (read_object(path) for path in self.root.glob("s-*/state.json")),
                key=lambda row: row["created_at"],
                reverse=True,
            )

    def detail(self, study_id: str) -> dict[str, Any]:
        with self.lock:
            root = child(self.root, study_id)
            if not (root / "state.json").is_file():
                raise KeyError("Étude introuvable.")
            state = read_object(root / "state.json")
            return {**state, "result": read_object(root / "result.json") if state["status"] == "completed" else None}

    def submit(self, dataset_name: str) -> dict[str, Any]:
        # Check manifest identity without waiting on a catalogue tape load in the HTTP handler.
        if dataset_name not in self.catalogue.names():
            raise ValueError("Corpus de recherche indisponible.")
        manifest = read_object(child(self.catalogue.root, dataset_name) / "manifest.json")
        if (manifest["window"]["start_ms"], manifest["window"]["end_ms"]) != (
            PROTOCOL["corpus_start_ms"],
            PROTOCOL["corpus_end_ms"],
        ):
            raise ValueError("Choisissez le corpus Polymarket du premier semestre 2024 pour R1.")
        excluded, protection = protected_ids(self.catalogue.root / "polyarchive2023")
        identifier = (
            "s-"
            + fingerprint(
                {
                    "protocol": PROTOCOL,
                    "dataset": manifest["dataset_hash"],
                    "protection": protection,
                    "excluded": sorted(excluded),
                }
            )[:24]
        )
        root = child(self.root, identifier)
        with self.lock:
            if (root / "state.json").exists():
                current = self.detail(identifier)
                if current["status"] in ("queued", "running", "completed"):
                    return current
            if any(row["status"] in ("queued", "running") for row in self.history()):
                raise RuntimeError("Une étude de signaux est déjà en cours.")
            state = {
                "study_id": identifier,
                "dataset": dataset_name,
                "status": "queued",
                "error": None,
                "created_at": datetime.now(UTC).isoformat(),
                "protocol_hash": fingerprint(PROTOCOL),
            }
            write_json(root / "protocol.json", PROTOCOL)
            write_json(root / "state.json", state)
            self.worker.submit(self._work, state, excluded, protection, str(manifest["dataset_hash"]))
            return dict(state)

    def _work(self, state: dict[str, Any], excluded: set[str], protection: str, expected_hash: str) -> None:
        root = child(self.root, state["study_id"])
        try:
            with self.lock:
                state["status"] = "running"
                write_json(root / "state.json", state)
            dataset = self.catalogue.load(state["dataset"])
            if dataset.manifest.dataset_hash != expected_hash:
                raise ValueError("Le corpus a changé après l'enregistrement du protocole.")
            result, observations = study(dataset, excluded=excluded, protection_hash=protection)
            result["corpus_coverage"] = read_object(
                self.catalogue.root / state["dataset"] / "archive" / "coverage.json"
            )
            result["reference_coverage"] = read_object(
                self.catalogue.root / "polyarchive2023" / "archive" / "coverage.json"
            )
            write_json(root / "observations.json", observations)
            write_json(root / "result.json", result)
            state["status"] = "completed"
        except Exception as error:
            state.update(status="failed", error=f"{type(error).__name__}: {error}")
        with self.lock:
            state["finished_at"] = datetime.now(UTC).isoformat()
            write_json(root / "state.json", state)

    def export(self, study_id: str, *, observations: bool = False) -> Path:
        if self.detail(study_id)["status"] != "completed":
            raise ValueError("L'étude doit être terminée avant export.")
        return child(self.root, study_id) / ("observations.json" if observations else "result.json")

    def close(self) -> None:
        self.worker.shutdown(wait=True)
