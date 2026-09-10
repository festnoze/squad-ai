"""The closed feature vocabulary a rule's predicates draw from (CONTRACTS_V2 18.1 and 18.2, package S2).

A rule is data, never code, and the whole point of that is that the same statement can be evaluated on
any bar of any dataset. That only holds if the names a predicate may use are closed and if every name
carries its unit and its bounds, so this module is the one place that answers three questions: which
feature names exist, which sensor block each of them lives in, and what an integer read of one looks
like when the sensor was never bought.

**Where the names come from.** 18.1 says it exactly: ``FEATURE_NAMES`` is the union of
``spec.features[*].name`` over the sensor catalogue, seventy-five names on the shipped fixture, unique
across sensors. The catalogue is S1's (``pmx.sensors.catalogue``) and its normative table is the contract
fixture ``tests/fixtures/contract/sensor.catalogue.json``, which S1 implements exactly. This module reads
S1's catalogue when it is importable and falls back to that fixture while S1 is being built, so the
vocabulary is the same seventy-five names either way and no second table is ever written down. When S1
lands, the fallback stops being reached and :func:`catalogue_source` says so; ``NotConfiguredError`` is
raised only when neither exists, which is a wheel without S1 rather than a tree mid-build.

**Reading a feature.** A block is fixed width and every position is an integer already clamped to its
bounds, so reading a feature is an index into the block of its sensor, and a missing input took the
catalogue's ``sentinel`` at sense time (ruling R285) rather than becoming a ``None`` a reader has to
infer. What this module still has to answer is the *absent sensor*: a diet that never bought ``hn`` has
no ``hn`` block at all, and :func:`read_feature` returns ``None`` there. ``Rule.fires`` turns that into
"does not fire" and ``Rule.readable_by`` filters the rule out before evaluation (ruling R279): the two
answers are different on purpose, and neither of them raises.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Protocol, runtime_checkable

from pmx.errors import NotConfiguredError

__all__ = (
    "FEATURES",
    "FEATURE_NAMES",
    "RE_FEATURE",
    "SENSOR_NAMES_IN_VOCABULARY",
    "FeatureBlock",
    "FeatureRef",
    "SensorBlockLike",
    "catalogue_source",
    "feature_ref",
    "is_feature",
    "read_feature",
    "sensors_for",
)

#: A feature name, as ``rule.v1.json``'s predicate spells it.
RE_FEATURE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")

#: The contract fixture that is 18.1's normative table, relative to the repository root.
_FIXTURE_RELATIVE = Path("tests") / "fixtures" / "contract" / "sensor.catalogue.json"


@runtime_checkable
class SensorBlockLike(Protocol):
    """What this module needs of S1's ``SensorBlock``: which sensor it is and its integer values.

    A protocol rather than an import, for two reasons. S1 owns ``SensorBlock`` and this package may not
    define a second one; and the tester, the miner and a test fixture all hand over blocks that were
    never sensed by an agent, so binding to the class would tie a projection to the engine. The members
    are read-only properties, which a frozen dataclass satisfies and a mutable one does too.
    """

    @property
    def sensor(self) -> str: ...

    @property
    def values(self) -> tuple[int, ...]: ...


@dataclass(frozen=True, slots=True)
class FeatureBlock:
    """A block of integers under a sensor name: the minimal :class:`SensorBlockLike` a projection needs.

    S1's ``SensorBlock`` carries the sensor's ``version`` and the market id as well, and satisfies the
    same protocol. This one exists so a ledger, a fixture or the miner's row table can carry the values a
    rule reads without depending on a sensed observation, and so that a test can plant a block by hand.
    """

    sensor: str
    values: tuple[int, ...]

    def to_dict(self) -> dict[str, object]:
        return {"sensor": self.sensor, "values": list(self.values)}


@dataclass(frozen=True, slots=True)
class FeatureRef:
    """Where one feature lives and what an integer of it means (18.1's ``SensorFeatureSpec``, narrowed).

    ``index`` is the position inside its sensor's block, ``lo`` and ``hi`` the bounds a predicate value
    must sit inside, and ``sentinel`` the value a missing input took when the block was sensed. The four
    are what a predicate needs; the rest of the catalogue entry (its description, its ``features.v1``
    position, its ``asof_only`` flag) belongs to S1 and is not restated here.
    """

    name: str
    sensor: str
    index: int
    unit: str
    lo: int
    hi: int
    sentinel: int

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "sensor": self.sensor,
            "index": self.index,
            "unit": self.unit,
            "lo": self.lo,
            "hi": self.hi,
            "sentinel": self.sentinel,
        }


def _repo_root() -> Path:
    """The tree this package was installed from, editable or not: ``src/pmx/rules`` up three levels."""
    return Path(__file__).resolve().parents[3]


def _specs_from_catalogue() -> tuple[Sequence[Mapping[str, object]], str] | None:
    """S1's catalogue, rendered as the fixture renders it, or ``None`` while S1 is being built."""
    try:
        module = import_module("pmx.sensors.catalogue")
    except ImportError:
        return None
    sensors = getattr(module, "SENSORS", None)
    if not isinstance(sensors, Mapping):
        return None
    specs: list[Mapping[str, object]] = []
    for spec in sensors.values():
        rendered = spec.to_dict()
        if not isinstance(rendered, Mapping):  # pragma: no cover - S1's to_dict returns a dict
            return None
        specs.append(rendered)
    return tuple(specs), "pmx.sensors.catalogue"


def _specs_from_fixture() -> tuple[Sequence[Mapping[str, object]], str] | None:
    """18.1's normative table, read from the contract fixture, or ``None`` when it is not on disk."""
    path = _repo_root() / _FIXTURE_RELATIVE
    if not path.is_file():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):  # pragma: no cover - the fixture is an object
        return None
    sensors = document.get("sensors")
    if not isinstance(sensors, list):  # pragma: no cover - the fixture carries a list
        return None
    specs: list[Mapping[str, object]] = []
    for spec in sensors:
        if not isinstance(spec, Mapping):  # pragma: no cover - every entry is an object
            return None
        specs.append(spec)
    return tuple(specs), str(_FIXTURE_RELATIVE.as_posix())


def _load() -> tuple[dict[str, FeatureRef], str]:
    """The vocabulary and the name of what it was read from."""
    loaded = _specs_from_catalogue() or _specs_from_fixture()
    if loaded is None:
        raise NotConfiguredError(
            "the sensor catalogue is unreadable: neither pmx.sensors.catalogue (S1) nor the contract "
            "fixture is available, so the rule vocabulary has no names",
            fixture=str(_FIXTURE_RELATIVE.as_posix()),
        )
    specs, source = loaded
    features: dict[str, FeatureRef] = {}
    for spec in specs:
        sensor = str(spec["name"])
        entries = spec["features"]
        if not isinstance(entries, list):  # pragma: no cover - the catalogue carries a list
            raise NotConfiguredError("a sensor spec carries no feature list", sensor=sensor)
        for position, entry in enumerate(entries):
            if not isinstance(entry, Mapping):  # pragma: no cover - every entry is an object
                raise NotConfiguredError("a sensor feature is not an object", sensor=sensor)
            name = str(entry["name"])
            if name in features:
                raise NotConfiguredError(
                    "a feature name occurs under two sensors, so the vocabulary is not a union",
                    feature=name,
                    sensors=(features[name].sensor, sensor),
                )
            index = int(entry.get("index", position))
            features[name] = FeatureRef(
                name=name,
                sensor=sensor,
                index=index,
                unit=str(entry["unit"]),
                lo=int(entry["lo"]),
                hi=int(entry["hi"]),
                sentinel=int(entry["sentinel"]),
            )
    return features, source


_FEATURES, _SOURCE = _load()

#: Every feature of the catalogue, by name: the closed vocabulary of 18.2's predicates.
FEATURES: Mapping[str, FeatureRef] = _FEATURES

#: The vocabulary's names, sorted, unique across sensors (18.1: seventy-five on the shipped catalogue).
FEATURE_NAMES: tuple[str, ...] = tuple(sorted(_FEATURES))

#: The sensors the vocabulary spans, sorted: what ``Rule.readable_by`` compares a diet against.
SENSOR_NAMES_IN_VOCABULARY: tuple[str, ...] = tuple(sorted({ref.sensor for ref in _FEATURES.values()}))


def catalogue_source() -> str:
    """Where the vocabulary was read from: ``"pmx.sensors.catalogue"`` once S1 ships, else the fixture."""
    return _SOURCE


def is_feature(name: str) -> bool:
    """Is ``name`` one of the catalogue's features? The one membership test the rest of S2 calls."""
    return name in _FEATURES


def feature_ref(name: str) -> FeatureRef:
    """The catalogue entry of ``name``.

    Raises:
        KeyError: If the name is outside the vocabulary. Callers that owe the contract a
            ``RuleRefusedError`` (``Rule.__post_init__``, ``rule_from_dict``) check :func:`is_feature`
            first and raise their own, so the refusal names the rule and not the mapping.
    """
    return _FEATURES[name]


def sensors_for(features: Iterable[str]) -> tuple[str, ...]:
    """The sorted, unique sensors that carry ``features``: a rule's ``required_sensors``.

    An unknown name contributes nothing rather than raising, because the one caller that can meet one
    (``Rule.readable_by`` on a rule built before a catalogue bump) must answer "no diet can read this"
    and not crash a hive view.
    """
    return tuple(sorted({_FEATURES[name].sensor for name in features if name in _FEATURES}))


def read_feature(name: str, blocks: Mapping[str, SensorBlockLike]) -> int | None:
    """The integer ``name`` takes in ``blocks``, or ``None`` when those blocks cannot answer.

    ``None`` means the sensor is absent from the blocks handed over (an unbought diet, ruling R279) or
    the name is outside the vocabulary. It never means "missing input": a missing input is the
    catalogue's ``sentinel`` and is an ordinary integer a predicate compares against, which is what
    keeps a block fixed width and a rule total.
    """
    ref = _FEATURES.get(name)
    if ref is None:
        return None
    block = blocks.get(ref.sensor)
    if block is None:
        return None
    values = block.values
    if ref.index >= len(values):
        return None
    return int(values[ref.index])
