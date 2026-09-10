"""The ``macro_releases`` sensor of CONTRACTS_V2 18.1 (package S1): ALFRED vintages and CBOE prints.

Its two sources are ``fred`` (second stamped, no lag) and ``cboe`` (day stamped, six hours late), so its
derived pair is a **day and six hours** and not a second and nothing (ruling R287). That is the whole
point of the derivation: the column a reader consults when asking whether a sensor can leak names the
sensor's worst source. On a minute dataset the ``cboe`` half is inadmissible (18.3), the build drops it,
and the derived pair is recomputed over what the dataset actually carries.

Two of the four features have no input in ``SensorInputs`` (12.11):

* ``bars_to_next_release`` needs the release calendar of 17.7, which the declaration does not carry, so
  it reads its sentinel, its ``hi`` of ``100000`` (nothing scheduled is arbitrarily far away);
* ``release_revision_abs_bp`` needs two vintages of one observation, and ``NewsView`` carries a headline
  and a body rather than a vintage pair, so it reads ``0``.

Both are reported as contract issues. ``vix_last_milli`` reads the ``value=<number>`` field the release
line carries when the dataset has a ``cboe`` item, and its sentinel otherwise.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from pmx.sensors.catalogue import SensorBlock, SensorInputsLike, SensorSpec, block_of
from pmx.types import NewsView, interval_ms

_FRED = "fred"
_CBOE = "cboe"
#: The numeric field of a release line. A decimal string, never a float: reading a provider's number as a
#: float would make the same tape hash differently on two machines (7.2).
RE_RELEASE_VALUE = re.compile(r"value=(-?[0-9]{1,12}(?:\.[0-9]{1,6})?)")


def _value_milli(item: NewsView) -> int | None:
    match = RE_RELEASE_VALUE.search(item.text) or RE_RELEASE_VALUE.search(item.headline)
    if match is None:
        return None
    try:
        scaled = Decimal(match.group(1)) * Decimal(1_000)
    except InvalidOperation:  # pragma: no cover - the regex admits only decimal strings
        return None
    return int(scaled.to_integral_value(rounding=ROUND_HALF_UP))


def sense(view: SensorInputsLike, *, now_ms: int, spec: SensorSpec) -> SensorBlock:
    """``macro_releases``'s four features (18.1)."""
    releases = tuple(view.news.get(_FRED, ())) + tuple(view.news.get(_CBOE, ()))
    bars_since_last_release: int | None = None
    if releases:
        latest_ms = max(item.published_at_ms for item in releases)
        bars_since_last_release = max(0, now_ms - latest_ms) // interval_ms(view.meta.interval_min)
    vix_items = sorted(view.news.get(_CBOE, ()), key=lambda item: (item.published_at_ms, item.news_id))
    vix_last_milli: int | None = None
    for item in reversed(vix_items):
        vix_last_milli = _value_milli(item)
        if vix_last_milli is not None:
            break
    values: list[int | None] = [None, bars_since_last_release, None, vix_last_milli]
    return block_of(spec, view.meta.id, values)
