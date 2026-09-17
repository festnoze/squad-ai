"""Offline MVP preparation repairs old splits without rewriting its source or concealing damage."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from tests.test_builder import build

from pmx.data import loader
from pmx.data.loader import load_dataset, load_manifest, write_manifest
from pmx.data.prepare_mvp import main, prepare_mvp
from pmx.data.schema import load_schema, validator_for
from pmx.errors import DatasetHashMismatchError, FoldIntegrityError, InvalidConfigError


def _bytes(path: Path) -> dict[str, bytes]:
    return {str(item.relative_to(path)): item.read_bytes() for item in path.rglob("*") if item.is_file()}


def _historical_source(tmp_path: Path) -> Path:
    result = build(tmp_path / "source")
    manifest = result.manifest
    # Preserve the data hashes while reproducing the historical manifest's obsolete fold counts.
    changed = replace(
        manifest,
        split=replace(manifest.split, n_train=manifest.split.n_train + 1, n_validation=0),
        cohorts=None,
    )
    write_manifest(result.path, changed)
    return result.path


def test_prepare_repairs_folds_preserves_every_market_and_source_and_records_shortfall(tmp_path: Path) -> None:
    source = _historical_source(tmp_path)
    original = _bytes(source)
    with pytest.raises(FoldIntegrityError):
        load_dataset(source)
    out = tmp_path / "prepared"
    assert prepare_mvp(source, out) == out.resolve()
    dataset = load_dataset(out, verify=True)
    expected_ids = {item.stem for item in (source / "markets").glob("*.json")}
    assert {meta.id for meta in dataset.metas} == expected_ids
    assert all(meta.subject for meta in dataset.metas)
    assert any(meta.cohort_id for meta in dataset.metas)
    assert dataset.manifest.split.method == "count_quantile"
    assert dataset.manifest.taxonomy is not None and dataset.manifest.taxonomy["audit"] is None
    assert dataset.manifest.build is not None and dataset.manifest.build["status"] == "failed"
    assert not dataset.manifest.sealed
    assert load_manifest(source).dataset_hash in dataset.manifest.notes
    for market_id in expected_ids:
        before = json.loads((source / "markets" / f"{market_id}.json").read_text(encoding="utf-8"))
        after = json.loads((out / "markets" / f"{market_id}.json").read_text(encoding="utf-8"))
        assert (after["bars"], after["trades"]) == (before["bars"], before["trades"])
    assert _bytes(source) == original

    first_output = _bytes(out)
    assert prepare_mvp(source, out) == out.resolve()
    assert _bytes(out) == first_output
    second = tmp_path / "prepared-again"
    prepare_mvp(source, second)
    assert _bytes(second) == first_output


def test_prepare_refuses_tampered_source_before_creating_output(tmp_path: Path) -> None:
    source = _historical_source(tmp_path)
    market = next((source / "markets").glob("*.json"))
    market.write_bytes(market.read_bytes() + b" ")
    out = tmp_path / "prepared"
    with pytest.raises(DatasetHashMismatchError, match="source bytes"):
        prepare_mvp(source, out)
    assert not out.exists()


def test_existing_derivative_is_verified_and_never_silently_overwritten(tmp_path: Path) -> None:
    source = _historical_source(tmp_path)
    out = prepare_mvp(source, tmp_path / "prepared")
    market = next((out / "markets").glob("*.json"))
    market.write_bytes(market.read_bytes() + b" ")
    corrupted = _bytes(out)
    with pytest.raises(DatasetHashMismatchError):
        prepare_mvp(source, out)
    assert _bytes(out) == corrupted


def test_verified_loading_validates_tapes_once_and_retains_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = build(tmp_path).path
    load_market = loader.load_market_file
    seen: list[Path] = []

    def counted(path: Path, **kwargs: object) -> object:
        seen.append(path)
        return load_market(path, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(loader, "load_market_file", counted)
    dataset = load_dataset(source, verify=True)
    for meta in dataset.metas:
        assert dataset.market(meta.id) is dataset.market(meta.id)
    assert len(seen) == len(dataset.metas)
    assert len(set(seen)) == len(seen)
    # A new reader still rejects modified bytes, including syntactically harmless changes.
    market = seen[0]
    market.write_bytes(market.read_bytes() + b" ")
    with pytest.raises(DatasetHashMismatchError):
        load_dataset(source, verify=True)


@pytest.mark.parametrize("relative", [".", "child", ".."])
def test_source_and_output_must_be_disjoint(tmp_path: Path, relative: str) -> None:
    source = tmp_path / "source"
    with pytest.raises(InvalidConfigError, match="disjoint"):
        prepare_mvp(source, source / relative)


def test_cli_reports_missing_source_and_does_not_publish_an_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "prepared"
    assert main(["--source", str(tmp_path / "missing"), "--out", str(out)]) == 1
    assert "MVP preparation failed" in capsys.readouterr().err
    assert not out.exists()


def test_expanded_market_validator_preserves_published_constraints(tmp_path: Path) -> None:
    source = build(tmp_path).path
    market = next((source / "markets").glob("*.json"))
    original = json.loads(market.read_text(encoding="utf-8"))
    published = Draft202012Validator(load_schema("market.v2.json"))
    optimized = validator_for("market.v2.json")
    candidates = [original]
    for section in ("bars", "trades"):
        if not original[section]:
            continue
        for key in original[section][0]:
            for value in (None, -1, 0, 10000, True, "bad", {}):
                changed = copy.deepcopy(original)
                changed[section][0][key] = value
                candidates.append(changed)
            changed = copy.deepcopy(original)
            del changed[section][0][key]
            candidates.append(changed)
        changed = copy.deepcopy(original)
        changed[section][0]["unexpected"] = 1
        candidates.append(changed)
    for payload in candidates:
        expected = sorted((str(error.absolute_path), error.message) for error in published.iter_errors(payload))
        actual = sorted((str(error.absolute_path), error.message) for error in optimized.iter_errors(payload))
        assert actual == expected
