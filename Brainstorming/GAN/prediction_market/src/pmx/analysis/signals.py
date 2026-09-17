"""Preregistered descriptive signal study. No search, simulated execution or held-out observations."""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, stdev
from typing import Any

from pmx.analysis.campaign import fingerprint, read_object
from pmx.types import Dataset, Market

HOUR = 3_600_000
START = 1_704_067_200_000  # 2024-01-01 UTC
END = 1_711_929_600_000  # 2024-04-01 UTC
CORPUS_END = 1_719_792_000_000  # 2024-07-01 UTC
PROTOCOL: dict[str, Any] = {
    "version": "signal-study.v1",
    "start_ms": START,
    "end_ms": END,
    "corpus_start_ms": START,
    "corpus_end_ms": CORPUS_END,
    "fold": "train",
    "calibration_anchor_hours": 24,
    "price_bin_width_bp": 1000,
    "reversal_windows_hours": [24, 48],
    "reversal_leg_min_bp": 300,
    "activity_observed_hours_min": 6,
    "activity_staleness_hours_max": 6,
    "variants": 28,
    "minimum_markets": 30,
    "minimum_weeks": 3,
    "minimum_target_coverage": 0.8,
    "screen_effect_bp": 100,
    "months": ["2024-01", "2024-02", "2024-03"],
    "selection": "First causal anchor per market and variant; activity filters that anchor, never searches again.",
    "uncertainty": "Approximate normal 95% interval over equally weighted UTC-week means; descriptive, unadjusted.",
}
Json = dict[str, Any]


def protected_ids(root: Path) -> tuple[set[str], str]:
    """Read verified label metadata, never the older sealed market tapes. Supersets are safe."""
    manifest = read_object(root / "manifest.json")
    path = root / "archive" / "labels.jsonl"
    expected = next(row["sha256"] for row in manifest["files"] if row["path"] == "archive/labels.jsonl")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError("La métadonnée de protection 2023 ne correspond plus à son manifeste.")
    import json

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    excluded = {
        "polymarket-" + row["condition_id"]
        for row in rows
        if row.get("available_at_ms") is not None and row["available_at_ms"] >= manifest["split"]["validation_end_ms"]
    }
    return excluded, str(manifest["dataset_hash"])


def definitions() -> list[Json]:
    base = [
        {
            "key": f"calibration-{index}",
            "family": "calibration",
            "bin_low_bp": index * 1000,
            "label": f"Prix OUI {index * 10}–{(index + 1) * 10} %",
        }
        for index in range(10)
    ]
    base += [
        {
            "key": f"reversal-{hours}-{direction}",
            "family": "reversal",
            "horizon_hours": hours,
            "direction": direction,
            "label": f"Retournement {'haussier' if direction == 1 else 'baissier'} {hours} h",
        }
        for hours in (24, 48)
        for direction in (1, -1)
    ]
    return [
        {**row, "variant_id": f"{row['key']}-{activity}", "activity": activity}
        for row in base
        for activity in ("all", "active_fresh")
    ]


def market_observations(market: Market, *, cutoff: int) -> tuple[list[Json], Json]:
    # No future bars enter trigger construction, activity, or selection of an anchor.
    bars = {bar.t_ms: bar for bar in market.bars if bar.t_ms >= START and bar.t_ms + HOUR < cutoff}
    ordered = sorted(bars)
    observed = [time for time in ordered if bars[time].volume_milli > 0]
    observations: list[Json] = []
    seen: set[str] = set()
    last_observed: int | None = None
    recent: list[int] = []
    for time in ordered:
        bar = bars[time]
        if bar.volume_milli > 0:
            last_observed = time
            recent.append(time)
        recent = [value for value in recent if value > time - 24 * HOUR]
        age = (time - last_observed) // HOUR if last_observed is not None else None
        active = len(recent) >= 6 and age is not None and age <= 6
        common = {
            "market_id": market.id,
            "t_ms": time + HOUR,
            "month": datetime.fromtimestamp((time + HOUR) / 1000, UTC).strftime("%Y-%m"),
            "week": datetime.fromtimestamp((time + HOUR) / 1000, UTC).strftime("%G-W%V"),
            "price_bp": bar.close_bp,
            "observed_hours_24": len(recent),
            "staleness_hours": age,
            "active_fresh": active,
        }
        if time == market.bars[0].t_ms + 24 * HOUR:
            available = market.resolved_at_ms // HOUR * HOUR + HOUR
            reason = "label_after_cutoff" if available >= cutoff else None
            observations.append(
                {
                    **common,
                    "key": f"calibration-{min(9, bar.close_bp // 1000)}",
                    "target_ms": available,
                    "missing_reason": reason,
                    "outcome": market.resolution if reason is None else None,
                    "effect_bp": market.resolution * 10000 - bar.close_bp if reason is None else None,
                }
            )
        if bar.volume_milli <= 0:
            continue
        for hours in (24, 48):
            first, middle = bars.get(time - hours * HOUR), bars.get(time - hours // 2 * HOUR)
            if first is None or middle is None or first.volume_milli <= 0 or middle.volume_milli <= 0:
                continue
            down, up = first.close_bp - middle.close_bp, bar.close_bp - middle.close_bp
            direction = 1 if down >= 300 and up >= 300 else -1 if down <= -300 and up <= -300 else 0
            key = f"reversal-{hours}-{direction}"
            if direction == 0 or key in seen:
                continue
            seen.add(key)
            target_time = time + hours * HOUR
            target = bars.get(target_time)
            reason = (
                "target_after_cutoff"
                if target_time + HOUR >= cutoff
                else "target_after_resolution"
                if target_time >= market.resolved_at_ms // HOUR * HOUR
                else "target_without_observed_trade"
                if target is None or target.volume_milli <= 0
                else None
            )
            observations.append(
                {
                    **common,
                    "key": key,
                    "target_ms": target_time + HOUR,
                    "missing_reason": reason,
                    "outcome": None,
                    "effect_bp": direction * (target.close_bp - bar.close_bp)
                    if reason is None and target is not None
                    else None,
                }
            )
    return observations, {
        "market_id": market.id,
        "bars": len(ordered),
        "observed_hours": len(observed),
        "calibration_anchor_present": any(row["key"].startswith("calibration") for row in observations),
    }


def summary(definition: Json, observations: list[Json]) -> Json:
    selected = [
        row
        for row in observations
        if row["key"] == definition["key"] and (definition["activity"] == "all" or row["active_fresh"])
    ]
    usable = [row for row in selected if row["effect_bp"] is not None]
    weeks: dict[str, list[float]] = defaultdict(list)
    for row in usable:
        weeks[row["week"]].append(row["effect_bp"])
    weekly = [mean(values) for values in weeks.values()]
    interval = None
    if len(weekly) >= 3:
        margin = 1.96 * stdev(weekly) / math.sqrt(len(weekly))
        interval = [mean(weekly) - margin, mean(weekly) + margin]
    months = []
    for month in PROTOCOL["months"]:
        rows = [row for row in usable if row["month"] == month]
        months.append(
            {
                "month": month,
                "n": len(rows),
                "mean_effect_bp": mean(row["effect_bp"] for row in rows) if rows else None,
            }
        )
    effect = mean(row["effect_bp"] for row in usable) if usable else None
    coverage = len(usable) / len(selected) if selected else None
    enough = len(usable) >= 30 and len(weekly) >= 3 and coverage is not None and coverage >= 0.8
    screen = (
        enough
        and effect is not None
        and effect > 100
        and all(row["mean_effect_bp"] is not None and row["mean_effect_bp"] > 0 for row in months)
    )
    return {
        **definition,
        "n_anchors": len(selected),
        "n_markets": len(usable),
        "n_weeks": len(weekly),
        "target_coverage": coverage,
        "missing_reasons": dict(Counter(row["missing_reason"] for row in selected if row["missing_reason"])),
        "mean_effect_bp": effect,
        "weekly_mean_effect_bp": mean(weekly) if weekly else None,
        "weekly_interval_95_bp": interval,
        "months": months,
        "mean_price_bp": mean(row["price_bp"] for row in usable) if usable else None,
        "win_rate": mean(row["outcome"] for row in usable)
        if usable and definition["family"] == "calibration"
        else None,
        "status": "candidate_for_replication" if screen else "not_retained" if enough else "inconclusive",
    }


def study(dataset: Dataset, *, excluded: set[str], protection_hash: str) -> tuple[Json, list[Json]]:
    manifest = dataset.manifest
    if manifest.interval_min != 60 or manifest.window.start_ms != START or manifest.window.end_ms != CORPUS_END:
        raise ValueError(
            "R1 exige le corpus horaire du 1 janvier au 1 juillet 2024 ; aucun autre calendrier implicite."
        )
    cutoff = min(END, manifest.split.train_end_ms)
    if cutoff <= START:
        raise ValueError("Aucune période d'entraînement disponible dans la fenêtre R1.")
    observations = []
    coverage = []
    eligible = [
        meta
        for meta in dataset.metas
        if meta.fold == "train"
        and meta.kind == "binary"
        and meta.provider == "polymarket"
        and meta.id not in excluded
    ]
    for meta in sorted(eligible, key=lambda row: row.id):
        market = dataset.market(meta.id)
        if not isinstance(market, Market):
            raise ValueError("R1 accepte uniquement des contrats binaires.")
        rows, quality = market_observations(market, cutoff=cutoff)
        observations.extend(rows)
        coverage.append(quality)
    total = sum(row["bars"] for row in coverage)
    observed = sum(row["observed_hours"] for row in coverage)
    result = {
        "protocol": PROTOCOL,
        "protocol_hash": fingerprint(PROTOCOL),
        "dataset": manifest.name,
        "dataset_hash": manifest.dataset_hash,
        "protection_dataset_hash": protection_hash,
        "protected_ids_hash": fingerprint(sorted(excluded)),
        "protected_ids_count": len(excluded),
        "excluded_overlap": len([meta for meta in dataset.metas if meta.id in excluded]),
        "effective_cutoff_ms": cutoff,
        "rows": [summary(definition, observations) for definition in definitions()],
        "coverage": {
            "eligible_train_markets": len(eligible),
            "markets_with_bars": sum(row["bars"] > 0 for row in coverage),
            "bars": total,
            "observed_hours": observed,
            "observed_fraction": observed / total if total else None,
            "calibration_anchors": sum(row["calibration_anchor_present"] for row in coverage),
        },
        "observations_hash": fingerprint(observations),
        "limitations": [
            "Étude descriptive sur un adaptateur conditionné aux marchés résolus, avec exclusions conservées.",
            "28 variantes et groupes d'activité imbriqués : aucune correction de multiplicité ni certification R2.",
            "Intervalles normaux approximatifs de moyennes hebdomadaires ; dépendance événementielle inconnue.",
            "Effets bruts, sans exécution, frais, spread ou rendement du capital immobilisé.",
            "Cibles exactes manquantes conservées : leur disponibilité future peut sélectionner le sous-échantillon.",
            "Une présélection descriptive propose une réplication ; elle ne démontre pas un avantage exploitable.",
        ],
    }
    return result, observations
