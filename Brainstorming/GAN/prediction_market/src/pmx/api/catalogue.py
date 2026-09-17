"""Verified local dataset access; only the MVP research derivative is made public."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from threading import RLock
from typing import Any

from pmx.data.loader import load_dataset
from pmx.types import Dataset, Market, MarketMeta

IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")
VISIBLE_FOLDS = ("train", "validation")
LIMITATIONS = [
    "Exploration historique : aucune certification de performance ou de rentabilité.",
    "Décisions sur barres complétées et exécution simulée à la barre suivante.",
    "Volume historique et liquidité simulée ne prouvent pas la disponibilité du carnet d'ordres.",
    "Les devises des fournisseurs restent séparées, sans conversion ni comparaison monétaire directe.",
    "Les marchés scellés sont exclus de la consultation et des simulations MVP.",
]


def valid_identifier(value: str) -> bool:
    return IDENTIFIER.fullmatch(value) is not None


def market_summary(dataset: Dataset, meta: MarketMeta) -> dict[str, Any]:
    market = dataset.market(meta.id)
    if not isinstance(market, Market):
        raise ValueError("Le MVP accepte uniquement des marchés binaires.")
    return {
        "id": meta.id,
        "question": market.question,
        "category": meta.category,
        "provider": meta.provider,
        "currency": market.currency,
        "fold": meta.fold,
        "source": market.source,
        "created_at_ms": meta.created_at_ms,
        "close_at_ms": meta.close_at_ms,
        "close_time_verified": meta.close_time_verified,
        "resolved_at_ms": meta.resolved_at_ms,
        "resolution": meta.resolution,
        "n_bars": len(market.bars),
        "n_trades": len(market.trades),
        "volume_milli": sum(bar.volume_milli for bar in market.bars),
        "subjects": list(meta.subject),
        "structure": meta.structure,
        "horizon": meta.horizon,
        "cohort_id": meta.cohort_id,
    }


class Catalogue:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._datasets: dict[str, Dataset] = {}
        self._summaries: dict[str, list[dict[str, Any]]] = {}
        self._lock = RLock()

    def names(self) -> list[str]:
        names = []
        for path in self.root.glob("*/manifest.json"):
            name = path.parent.name
            if not valid_identifier(name) or not path.resolve().is_relative_to(self.root):
                continue
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(manifest, dict) and manifest.get("purpose") == "research":
                names.append(name)
        return sorted(names)

    def load(self, name: str) -> Dataset:
        if not valid_identifier(name) or name not in self.names():
            raise KeyError("Dataset de recherche indisponible. Préparez un corpus local vérifié.")
        with self._lock:
            if name not in self._datasets:
                dataset = load_dataset(self.root / name, verify=True)
                if dataset.purpose != "research":
                    raise ValueError("Le MVP demande un dataset de recherche vérifié.")
                self._datasets[name] = dataset
            return self._datasets[name]

    def markets(self, name: str) -> list[dict[str, Any]]:
        with self._lock:
            if name not in self._summaries:
                dataset = self.load(name)
                self._summaries[name] = [
                    market_summary(dataset, meta)
                    for meta in sorted(dataset.metas, key=lambda row: row.id)
                    if meta.fold in VISIBLE_FOLDS and meta.kind == "binary"
                ]
            return self._summaries[name]

    def summary(self, name: str) -> dict[str, Any]:
        dataset = self.load(name)
        manifest = dataset.manifest
        visible = [meta for meta in dataset.metas if meta.fold in VISIBLE_FOLDS]
        coverage_path = self.root / name / "archive" / "coverage.json"
        coverage = json.loads(coverage_path.read_text(encoding="utf-8")) if coverage_path.is_file() else None
        limitations = list(LIMITATIONS)
        if coverage is not None:
            limitations.extend([
                "Archive historique Polymarket v1 ; l'adaptateur affiché contient les marchés résolus admissibles.",
                "Frais de scénario de 20 points de base ; aucun barème historique complet n'est revendiqué.",
                "Dates de clôture inférées, relations entre événements inconnues et carnets absents.",
            ])
        if manifest.notes:
            limitations.append(manifest.notes)
        return {
            "name": manifest.name,
            "dataset_hash": manifest.dataset_hash,
            "freeze_date": manifest.freeze_date,
            "interval_min": manifest.interval_min,
            "n_markets": len(dataset.metas),
            "n_visible_markets": len(visible),
            "providers": sorted({meta.provider for meta in visible}),
            "categories": sorted({meta.category for meta in visible}),
            "counts_by_provider": dict(Counter(meta.provider for meta in visible)),
            "counts_by_fold": dict(Counter(meta.fold for meta in dataset.metas)),
            "limitations": limitations,
            "coverage": coverage,
        }

    def detail(self, name: str, market_id: str) -> dict[str, Any]:
        dataset = self.load(name)
        meta = next((row for row in dataset.metas if row.id == market_id and row.fold in VISIBLE_FOLDS), None)
        if meta is None:
            raise KeyError("Marché indisponible dans les données exploratoires.")
        market = dataset.market(market_id)
        return {
            "market": market_summary(dataset, meta),
            "bars": [
                {
                    key: getattr(bar, key)
                    for key in ("t_ms", "open_bp", "high_bp", "low_bp", "close_bp", "volume_milli")
                }
                for bar in market.bars
            ],
            "news": [
                {
                    "id": item.news_id,
                    "published_at_ms": item.published_at_ms,
                    "visible_from_ms": item.visible_from_ms,
                    "source": item.source,
                    "text": item.text,
                    "url": item.url,
                }
                for item in dataset.news_for(market_id, dataset.manifest.freeze_ms)
            ],
        }
