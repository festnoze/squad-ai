"""Compact post-campaign evidence, without reopening tapes or changing research results."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

REPORT_VERSION = "campaign-review.v1"
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")
Json = dict[str, Any]


def read_object(path: Path) -> Json:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object: {path.name}")
    return value


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def child(root: Path, identifier: str) -> Path:
    if not ID.fullmatch(identifier):
        raise ValueError("Invalid artifact identifier")
    path = (root / identifier).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Artifact is outside its root")
    return path


def period_summary(row: Json) -> Json:
    keys = ("period", "fold", "t0_ms", "t1_ms", "pnl_cents", "fees_cents", "max_drawdown_bp",
            "n_fills", "n_markets", "n_settled_markets", "run_id", "journal_hash")
    return {**{key: row.get(key) for key in keys},
            "pnl_plus_fees_same_fills_cents": row["pnl_cents"] + row["fees_cents"],
            "distinct_traded_markets": len(set(row.get("traded_market_ids", [])))}


def market_attribution(run: Json, candidate_id: str, run_root: Path) -> Json:
    path = child(run_root, run["run_id"]) / "results.json"
    result = read_object(path)
    rows = [row for row in result["per_market"] if row["agent_id"] == candidate_id]
    traded = [row for row in rows if row["traded"]]
    losses = sorted((row for row in traded if row["realised_pnl_cents"] < 0),
                    key=lambda row: row["realised_pnl_cents"])
    wins = sorted((row for row in traded if row["realised_pnl_cents"] > 0),
                  key=lambda row: -row["realised_pnl_cents"])
    def compact(row: Json) -> Json:
        return {**{key: row[key] for key in ("market_id", "realised_pnl_cents", "fees_cents")},
                "fill_events_including_zero_size": row["n_fills"]}
    return {
        "run_id": run["run_id"], "projection_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "markets": len(rows), "traded_markets": len(traded), "winning_traded_markets": len(wins),
        "losing_traded_markets": len(losses), "zero_pnl_traded_markets": len(traded) - len(wins) - len(losses),
        "realised_pnl_sum_cents": sum(row["realised_pnl_cents"] for row in rows),
        "marked_period_pnl_cents": run["pnl_cents"],
        "attribution_note": "Per-market realised PnL can differ from marked period equity if inventory is open.",
        "fill_count_note": "Projection fill events include zero-size/unfilled events; period n_fills counts "
                           "positive executed quantities only. Do not interpret these as the same count.",
        "gross_losses_cents": -sum(row["realised_pnl_cents"] for row in losses),
        "worst_five_losses_cents": -sum(row["realised_pnl_cents"] for row in losses[:5]),
        "worst_markets": [compact(row) for row in losses[:5]],
        "best_markets": [compact(row) for row in wins[:5]],
        "mean_agent_brier_micro": sum(row["agent_brier_tw_micro"] for row in rows) / len(rows) if rows else None,
        "mean_market_brier_micro": sum(row["market_brier_tw_micro"] for row in rows) / len(rows) if rows else None,
    }


def evidence_packet(campaign: Json, *, run_root: Path, dataset_root: Path) -> Json:
    if campaign.get("status") != "completed":
        raise ValueError("Analyse disponible seulement après la fin complète de la campagne.")
    dataset = child(dataset_root, campaign["dataset"])
    coverage_path = dataset / "archive" / "coverage.json"
    coverage = None
    if coverage_path.exists():
        manifest = read_object(dataset / "manifest.json")
        if manifest["dataset_hash"] != campaign["dataset_hash"]:
            raise ValueError("Le dataset ne correspond plus à la campagne.")
        expected = next(row["sha256"] for row in manifest["files"] if row["path"] == "archive/coverage.json")
        if hashlib.sha256(coverage_path.read_bytes()).hexdigest() != expected:
            raise ValueError("Le rapport de couverture a changé depuis la campagne.")
        coverage = read_object(coverage_path)
    candidates = []
    attribution = []
    missing = []
    for row in campaign["candidates"]:
        train = [period_summary(period) for period in row["train_results"]]
        validation = [period_summary(period) for period in row["validation_results"]]
        candidates.append({
            **{key: row.get(key) for key in ("candidate_id", "trial_number", "family", "parameters", "status",
                                             "objective", "selected", "rejection_reasons", "rule_text", "error",
                                             "validation_status", "validation_error")},
            "train_periods": train, "validation_periods": validation,
            "training_sum_independent_periods_cents": sum(period["pnl_cents"] for period in train),
        })
        if row["selected"]:
            for period in row["validation_results"]:
                try:
                    attribution.append(market_attribution(period, row["candidate_id"], run_root))
                except (OSError, KeyError, ValueError) as error:
                    missing.append(f"Projection {period['run_id']}: {type(error).__name__}")
    baseline = campaign.get("baseline", {}).get("objective", 0)
    notes = []
    if campaign.get("discovery_version") == "discovery.v1":
        notes.append("Legacy discovery.v1: sparse/sampled mining rows used index-based drift horizons, so a declared "
                     "one-bar target could span several hours. This affects symbolic proposals, not deterministic "
                     "price strategies' fill accounting. Reassess symbolic results with timestamp-aligned targets.")
    return {
        "schema": REPORT_VERSION, "campaign_id": campaign["campaign_id"],
        "campaign_sha256": fingerprint(campaign), "dataset": campaign["dataset"],
        "dataset_hash": campaign["dataset_hash"], "currency": campaign["currency"],
        "engine_version": campaign.get("engine_version"), "discovery_version": campaign.get("discovery_version"),
        "config": campaign["config"], "mining": campaign.get("mining"),
        "baseline_objective": baseline, "objective_name": campaign.get("objective_name"),
        "trial_status_counts": dict(Counter(row["status"] for row in campaign["candidates"])),
        "eligible_above_cash_baseline": sum(row["status"] == "completed" and row.get("objective") is not None
                                            and row["objective"] > baseline for row in campaign["candidates"]),
        "candidates": candidates, "validation_attribution": attribution, "coverage": coverage,
        "missing_evidence": missing, "known_integrity_notes": notes,
        "interpretation_rules": [
            "Only selected candidates were evaluated on validation. Unselected validation is unknown, not zero.",
            "Pnl plus fees holds recorded fills fixed; it is not a new zero-fee backtest.",
            "Training totals sum independent resets; compare duration, activity and exposure before generalizing.",
            "No p-value, causal explanation, optimality or independent-event claim follows from these aggregates.",
            "Positive return alone is not evidence of edge. Reusing inspected validation makes it development data.",
            "The review may propose tests but cannot change code, parameters, campaign evidence or launch searches.",
        ],
        "limitations": campaign.get("limitations", []),
    }
