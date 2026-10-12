"""Current admission file agrees with state; raw historical reports are retained."""
import json

import pytest

from tests.test_final_cache_current_image_counterreview import (
    test_historical_final_cache_never_admits_unavailable_or_changed_image as counterexample,
)


@pytest.mark.parametrize("problem", ["missing", "cmd_drift"])
async def test_current_receipt_never_remains_pass_after_image_revalidation_failure(tmp_path, monkeypatch, problem):
    # Execute the independent invariant unchanged, then add this receipt check.
    await counterexample(tmp_path, monkeypatch, True, problem)
    paths = list((tmp_path/"workspace"/".autospec-supervisor").rglob("final-admission.json"))
    assert len(paths) == 1
    receipt = json.loads(paths[0].read_bytes())
    assert receipt["status"] == "NOT_VERIFIED" and receipt["findings"]
