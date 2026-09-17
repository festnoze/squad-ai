"""Post-campaign reviews: lifecycle, evidence accounting, subscription and isolation boundaries."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pmx import cli_mvp
from pmx.analysis.campaign import evidence_packet, read_object
from pmx.api.analyses import AnalysisService
from pmx.api.app import create_app
from pmx.api.service import write_json
from pmx.llm import campaign_review

REPORT = {
    "summary": "Les candidats ne dépassent pas le cash.", "verdict": "Aucun avantage démontré.",
    "findings": [{"title": "Frais", "evidence": "Perte de 10 centimes, frais de 2.",
                  "interpretation": "Déficit aussi à exécutions identiques avant frais."}],
    "next_tests": [{"priority": "P0", "hypothesis": "La densité modifie le résultat.",
                    "protocol": "Comparer des cohortes définies avant le test.",
                    "success_criterion": "Résultat net positif."}],
    "limitations": ["Simulation sans carnet."],
}


def campaign(root: Path) -> dict[str, Any]:
    value = {
        "campaign_id": "c-test", "status": "completed", "dataset": "sample", "dataset_hash": "abc",
        "currency": "usdc", "config": {"bankroll_cents": 100000}, "discovery_version": "discovery.v1",
        "candidates": [{"candidate_id": "strategy-test", "trial_number": 0, "family": "trend",
                        "status": "completed", "objective": -1, "selected": True, "rejection_reasons": [],
                        "train_results": [{"pnl_cents": 1, "fees_cents": 2}],
                        "validation_results": [{"run_id": "r-test", "pnl_cents": -10, "fees_cents": 2}]}],
    }
    write_json(root / "campaigns" / "c-test" / "campaign.json", value)
    return value


def wait_review(service: AnalysisService, identifier: str = "c-test") -> dict[str, Any]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        result = service.detail(identifier)
        if result["status"] not in ("queued", "running"):
            return result
        time.sleep(0.01)
    raise AssertionError("Review worker did not finish")


def test_real_accounting_packet_preserves_absent_validation_and_fixed_fill_fee_meaning(tmp_path: Path) -> None:
    c = campaign(tmp_path)
    c["candidates"].append({"candidate_id": "unselected", "status": "rejected", "selected": False,
                            "train_results": [], "validation_results": []})
    packet = evidence_packet(c, run_root=tmp_path, dataset_root=tmp_path / "data")
    assert packet["eligible_above_cash_baseline"] == 0
    assert packet["candidates"][0]["validation_periods"][0]["pnl_plus_fees_same_fills_cents"] == -8
    assert packet["candidates"][1]["validation_periods"] == []
    assert packet["missing_evidence"]
    assert packet["known_integrity_notes"]


def test_review_once_per_result_persisted_exports_and_no_automatic_historical_backfill(tmp_path: Path) -> None:
    calls = []
    c = campaign(tmp_path)
    def reviewer(packet: dict[str, Any], _path: Path) -> dict[str, Any]:
        calls.append(packet)
        return REPORT
    service = AnalysisService(tmp_path / "data", tmp_path, reviewer=reviewer)
    try:
        service.configure(enabled=True)
        service.recover()
        assert service.detail("c-test")["status"] == "not_requested"
        service.enqueue_auto(c)
        done = wait_review(service)
        assert done["status"] == "completed", done
        service.enqueue_auto(c)
        service.submit("c-test", retry=True)
        assert len(calls) == 1
        assert "Aucun avantage" in service.export("c-test").read_text(encoding="utf-8")
        assert read_object(service.export("c-test", evidence=True))["campaign_id"] == "c-test"
        assert read_object(tmp_path / "campaigns/c-test/campaign.json") == c
    finally:
        service.close()
    restored = AnalysisService(tmp_path / "data", tmp_path, reviewer=reviewer)
    try:
        restored.recover()
        assert restored.detail("c-test")["report"] == REPORT
        assert len(calls) == 1
    finally:
        restored.close()


def test_failed_llm_does_not_fail_campaign_or_loop_and_can_retry(tmp_path: Path) -> None:
    calls = []
    c = campaign(tmp_path)
    def fail(_packet: dict[str, Any], _path: Path) -> dict[str, Any]:
        calls.append(1)
        raise RuntimeError("Quota temporairement indisponible")
    service = AnalysisService(tmp_path / "data", tmp_path, reviewer=fail)
    try:
        service.configure(enabled=True)
        service.enqueue_auto(c)
        assert wait_review(service)["status"] == "failed"
        service.enqueue_auto(c)
        assert len(calls) == 1
        assert read_object(tmp_path / "campaigns/c-test/campaign.json")["status"] == "completed"
        service.reviewer = lambda _packet, _path: REPORT
        service.submit("c-test", retry=True)
        assert wait_review(service)["status"] == "completed"
    finally:
        service.close()


def test_interrupted_review_requires_explicit_retry_and_incomplete_campaign_is_rejected(tmp_path: Path) -> None:
    c = campaign(tmp_path)
    write_json(tmp_path / "analyses/c-test/state.json", {"campaign_id": "c-test", "status": "running"})
    service = AnalysisService(tmp_path / "data", tmp_path, reviewer=lambda _packet, _path: REPORT)
    try:
        service.recover()
        assert service.detail("c-test")["status"] == "failed"
        c["status"] = "cancelled"
        write_json(tmp_path / "campaigns/c-test/campaign.json", c)
        with pytest.raises(ValueError):
            service.submit("c-test")
        with pytest.raises(ValueError):
            service.detail("../secrets")
    finally:
        service.close()


def test_subscription_refuses_api_key_auth_and_removes_api_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-do-not-use")
    monkeypatch.setenv("CODEX_API_KEY", "test-key-do-not-use")
    monkeypatch.setattr(campaign_review, "codex_executable", lambda: "codex")
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command == ["codex", "login", "status"]
        assert "OPENAI_API_KEY" not in kwargs["env"] and "CODEX_API_KEY" not in kwargs["env"]
        return subprocess.CompletedProcess(command, 0, "Logged in using an API key", "")
    monkeypatch.setattr(campaign_review.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="ChatGPT"):
        campaign_review.subscription_status()


def test_http_analysis_settings_submission_and_exports(tmp_path: Path) -> None:
    campaign(tmp_path)
    app = create_app(dataset_root=tmp_path / "data", runs_dir=tmp_path)
    app.state.analysis_service.reviewer = lambda _packet, _path: REPORT
    with TestClient(app) as client:
        assert not client.get("/api/analysis/settings").json()["enabled"]
        assert client.post("/api/analysis/settings", json={"enabled": "yes"}).status_code == 422
        assert client.post("/api/analysis/settings", json={"enabled": True}).json()["enabled"]
        assert client.post("/api/campaigns/c-test/analysis").status_code == 202
        assert wait_review(app.state.analysis_service)["status"] == "completed"
        assert client.get("/api/campaigns/c-test/analysis").json()["report"] == REPORT
        assert client.get("/api/campaigns/c-test/analysis/export").status_code == 200
        response = client.get("/api/campaigns/c-test/analysis/evidence")
        assert json.loads(response.content)["campaign_id"] == "c-test"


@pytest.mark.parametrize("cached", [False, True])
def test_cli_only_notifies_new_completed_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cached: bool,
) -> None:
    result = {"campaign_id": "c-test", "status": "completed"}
    if cached:
        write_json(tmp_path / "campaigns/c-test/campaign.json", result)
    monkeypatch.setattr(cli_mvp.Catalogue, "load", lambda *_args: object())
    monkeypatch.setattr(cli_mvp, "campaign_id_for", lambda *_args: "c-test")
    monkeypatch.setattr(cli_mvp, "run_campaign", lambda *_args, **_kwargs: result)
    calls = []

    class Reviews:
        def enqueue_auto(self, value: dict[str, Any]) -> None:
            calls.append(value)

        def close(self) -> None:
            pass

    monkeypatch.setattr(cli_mvp, "AnalysisService", lambda *_args: Reviews())
    assert cli_mvp.main(["search", "--runs-dir", str(tmp_path)]) == 0
    assert calls == ([] if cached else [result])
