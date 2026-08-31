"""The sealed held-out scenario bank and its access log (PRD 8, AC-P5, T3.5, A20).

PRD section 8: "Held-out: banque de scenarios scelles (jamais vus pendant
l'iteration), generes par les memes gabarits avec seeds reserves; tout acces est
journalise". AC-P5 turns that into a testable claim: a report must distinguish
iteration performance from sealed performance, and every access to the bank must
leave a trace.

The seal is structural, not a convention
----------------------------------------
:class:`HeldoutBank` is the **only** way to obtain a sealed seed, and the only
method that returns one is :meth:`HeldoutBank.draw`, which writes an access log
entry before it returns anything. There is no accessor that returns the reserved
seeds without logging, which is what makes
``test_heldout.py::test_access_is_logged_and_sealed`` a claim about the design
and not about the caller's discipline. A refused access is logged too, with
``granted=false`` and a reason: an attempt to reach the bank for training is
exactly the event an audit wants to see.

Two files, both append safe
---------------------------
* the **bank** (``path``) holds the reserved seeds per template, as one canonical
  JSON object. It is rewritten whole by :meth:`reserve` and never by
  :meth:`draw`: drawing does not consume a seed, because an evaluation run must
  be repeatable on the same sealed set.
* the **access log** (``access_log``) is JSONL, one canonical line per access,
  appended and never rewritten. It is the same shape
  :meth:`pxe.store.db.Store.save_heldout_access` mirrors into the
  ``heldout_registry`` table, which extracts ``template_id``, ``requester``,
  ``purpose`` and ``count`` and keeps the whole entry as a payload.

Both are written with ``encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE``
(section 4.2) so a bank sealed on Windows is byte identical to one sealed on
Linux, and both go through :func:`pxe.events.canonical_json`, which rejects a
float structurally: a seed is an integer and an audit trail carries no clock.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pxe.errors import HeldoutAccessError, InvalidConfigError, StoreError
from pxe.events import JOURNAL_ENCODING, JOURNAL_NEWLINE, canonical_json
from pxe.rng import RngTree, randint
from pxe.types import SEED_SPACE

__all__ = [
    "HELDOUT_BANK_VERSION",
    "HELDOUT_SUBSTREAM",
    "EVALUATION_PURPOSES",
    "HeldoutBank",
]

#: Version of the bank file layout. A change means an existing bank cannot be
#: read, which is deliberate: silently reinterpreting a sealed set is worse than
#: refusing it.
HELDOUT_BANK_VERSION = 1

#: The registered substream every reserved seed is drawn from (section 3.3).
HELDOUT_SUBSTREAM = "tournament.heldout"

#: The purposes that may reach the bank. Anything else is an iteration activity
#: and is refused: "jamais vus pendant l'iteration" is the whole property being
#: protected, and a free text purpose would make the seal advisory.
EVALUATION_PURPOSES: frozenset[str] = frozenset(
    {
        "evaluation",
        "ab_test",
        "promotion_check",
        "final_report",
    }
)

#: Upper bound of a reserved seed, exclusive. Seeds are unsigned **63** bit
#: integers because that is what ``MatchConfig.seed`` accepts and what a
#: portable signed ``BigInteger`` column can hold (section 3.1 and section
#: 7.20): a sealed seed that ``Store.save_match`` cannot persist would make the
#: whole AC-P5 held-out run unrecordable.
_SEED_SPACE = SEED_SPACE

#: Safety margin on the rejection loop of :meth:`HeldoutBank.reserve`. A
#: collision in a 64 bit space is astronomically unlikely, so exhausting this
#: many attempts means the generator is broken and the caller must hear about it
#: rather than loop forever.
_RESERVE_ATTEMPT_MARGIN = 1024


class HeldoutBank:
    """A sealed bank of scenario seeds plus its journalled access log (T3.5).

    Not thread safe, and deliberately so: the orchestrator process is the single
    writer of every projection (section 7.20) and the bank follows the same rule.
    """

    __slots__ = ("_access_log_path", "_entries", "_path", "_templates")

    def __init__(self, *, path: Path, access_log: Path) -> None:
        """Open (or create in memory) a bank and its access log.

        Neither file has to exist. An existing bank is read so that
        :meth:`reserve` extends it instead of replacing it, and an existing log
        is read so that ``access_index`` keeps counting across processes.

        Args:
            path: The bank file, canonical JSON.
            access_log: The access log file, canonical JSONL.

        Raises:
            StoreError: If either file exists but cannot be read as the shape
                this class writes.
        """
        self._path = Path(path)
        self._access_log_path = Path(access_log)
        self._templates: dict[str, list[int]] = _read_bank(self._path)
        self._entries: list[dict[str, Any]] = _read_access_log(self._access_log_path)

    def reserve(self, *, template_id: str, count: int, base_seed: int) -> tuple[int, ...]:
        """Seal ``count`` new seeds for one template and return them.

        The seeds are drawn from ``RngTree(base_seed).child("heldout/<template>")``
        on the registered ``tournament.heldout`` substream, so the same
        ``(template_id, base_seed)`` seals the same set on every machine, and two
        templates sealed from one base seed never share a seed by construction.
        A seed already in the bank for that template is skipped, which makes a
        repeated call extend the set rather than duplicate it.

        Reserving is **not** an access: it creates sealed material rather than
        revealing it, so it writes no access log entry.

        Args:
            template_id: Scenario template, for example ``"election"``.
            count: How many new seeds to seal, at least one.
            base_seed: Root seed of the derivation, an unsigned 63 bit integer.

        Returns:
            The newly sealed seeds, ascending.

        Raises:
            InvalidConfigError: If ``template_id`` is empty, ``count`` is below
                one, ``base_seed`` does not fit in 63 unsigned bits, or the
                rejection loop cannot find enough distinct seeds.
        """
        if not template_id:
            raise InvalidConfigError("a held-out reservation needs a template id")
        if count < 1:
            raise InvalidConfigError("count must be at least one", count=count)
        if not 0 <= base_seed < _SEED_SPACE:
            raise InvalidConfigError("base_seed must fit in 63 unsigned bits", base_seed=base_seed)
        existing = self._templates.setdefault(template_id, [])
        rng = RngTree(base_seed).child(f"heldout/{template_id}").fresh_substream(HELDOUT_SUBSTREAM)
        known = set(existing)
        fresh: list[int] = []
        attempts = 0
        budget = count * 64 + _RESERVE_ATTEMPT_MARGIN
        while len(fresh) < count:
            attempts += 1
            if attempts > budget:
                raise InvalidConfigError(
                    "could not seal enough distinct seeds",
                    template_id=template_id,
                    count=count,
                    attempts=attempts,
                )
            candidate = randint(rng, 0, _SEED_SPACE - 1)
            if candidate in known:
                continue
            known.add(candidate)
            fresh.append(candidate)
        existing.extend(fresh)
        existing.sort()
        _write_bank(self._path, self._templates)
        return tuple(sorted(fresh))

    def draw(self, *, template_id: str, count: int, requester: str, purpose: str) -> tuple[int, ...]:
        """Return sealed seeds for an evaluation run, logging the access.

        Every call appends exactly one access log entry, granted or refused,
        before the method returns or raises. Drawing does not consume a seed: an
        evaluation of two harnesses on the same sealed set must be comparable, so
        the same ``(template_id, count)`` always returns the same seeds, the
        ``count`` smallest of the template's sealed set.

        Args:
            template_id: Scenario template to draw from.
            count: How many seeds are needed, at least one.
            requester: Who is asking, for example a harness key or
                ``"pxe evolve run"``. Mandatory: an anonymous access is not an
                audit trail.
            purpose: One of :data:`EVALUATION_PURPOSES`.

        Returns:
            The seeds, ascending.

        Raises:
            InvalidConfigError: If ``count`` is below one. Nothing was accessed,
                so nothing is logged.
            HeldoutAccessError: If ``requester`` is empty, if ``purpose`` is not
                an evaluation purpose (AC-P5: the bank is unreachable during
                iteration), if the template holds no sealed seed, or if it holds
                fewer than ``count``. The refusal is logged first.
        """
        if count < 1:
            raise InvalidConfigError("count must be at least one", count=count)
        if not requester:
            self._log(template_id=template_id, count=count, requester=requester, purpose=purpose, reason="NO_REQUESTER")
            raise HeldoutAccessError("a held-out access must name its requester", purpose=purpose)
        if purpose not in EVALUATION_PURPOSES:
            self._log(
                template_id=template_id, count=count, requester=requester, purpose=purpose, reason="NOT_AN_EVALUATION"
            )
            raise HeldoutAccessError(
                "the held-out bank is sealed outside an evaluation run (AC-P5)",
                purpose=purpose,
                requester=requester,
                allowed=tuple(sorted(EVALUATION_PURPOSES)),
            )
        available = self._templates.get(template_id, [])
        if len(available) < count:
            self._log(
                template_id=template_id, count=count, requester=requester, purpose=purpose, reason="NOT_ENOUGH_SEEDS"
            )
            raise HeldoutAccessError(
                "the held-out bank has not sealed enough seeds for this template",
                template_id=template_id,
                requested=count,
                sealed=len(available),
            )
        seeds = tuple(sorted(available)[:count])
        self._log(
            template_id=template_id,
            count=count,
            requester=requester,
            purpose=purpose,
            reason="",
            seeds=seeds,
        )
        return seeds

    def access_log_entries(self) -> tuple[Mapping[str, Any], ...]:
        """Return the whole access log, oldest first.

        Returns:
            One read only mapping per access, in ``access_index`` order. The keys
            are ``access_index``, ``template_id``, ``requester``, ``purpose``,
            ``count``, ``granted``, ``reason`` and ``seeds``; the four
            :meth:`pxe.store.db.Store.save_heldout_access` promotes to columns are
            always present.
        """
        return tuple(MappingProxyType(dict(entry)) for entry in self._entries)

    def _log(
        self,
        *,
        template_id: str,
        count: int,
        requester: str,
        purpose: str,
        reason: str,
        seeds: tuple[int, ...] = (),
    ) -> None:
        """Append one access log entry, in memory and on disk.

        Args:
            template_id: Scenario template of the access.
            count: How many seeds were asked for.
            requester: Who asked.
            purpose: Why.
            reason: Empty when the access was granted, a stable upper case code
                otherwise.
            seeds: The seeds handed out, empty on a refusal.
        """
        entry: dict[str, Any] = {
            "access_index": len(self._entries) + 1,
            "template_id": template_id,
            "requester": requester,
            "purpose": purpose,
            "count": int(count),
            "granted": not reason,
            "reason": reason,
            "seeds": [int(seed) for seed in seeds],
        }
        self._entries.append(entry)
        self._access_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._access_log_path.open("a", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
            handle.write(canonical_json(entry) + JOURNAL_NEWLINE)


def _read_bank(path: Path) -> dict[str, list[int]]:
    """Read a bank file, or return an empty bank when it does not exist.

    Args:
        path: The bank file.

    Returns:
        Template id to ascending sealed seeds.

    Raises:
        StoreError: If the file exists but is not a bank of the current version.
    """
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding=JOURNAL_ENCODING))
    except (OSError, json.JSONDecodeError) as exc:
        raise StoreError("the held-out bank file could not be read", path=str(path)) from exc
    if not isinstance(raw, dict) or raw.get("version") != HELDOUT_BANK_VERSION:
        raise StoreError("not a held-out bank of the expected version", path=str(path))
    templates = raw.get("templates")
    if not isinstance(templates, dict):
        raise StoreError("the held-out bank has no templates object", path=str(path))
    out: dict[str, list[int]] = {}
    for template_id in sorted(templates):
        seeds = templates[template_id]
        if not isinstance(seeds, list) or any(not isinstance(seed, int) or isinstance(seed, bool) for seed in seeds):
            raise StoreError("a held-out template must hold a list of integer seeds", template_id=template_id)
        out[str(template_id)] = sorted(int(seed) for seed in seeds)
    return out


def _write_bank(path: Path, templates: Mapping[str, list[int]]) -> None:
    """Rewrite the bank file whole, canonically.

    Args:
        path: The bank file.
        templates: Template id to sealed seeds.
    """
    payload = {
        "version": HELDOUT_BANK_VERSION,
        "templates": {template_id: sorted(templates[template_id]) for template_id in sorted(templates)},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        handle.write(canonical_json(payload) + JOURNAL_NEWLINE)


def _read_access_log(path: Path) -> list[dict[str, Any]]:
    """Read an access log, or return an empty one when it does not exist.

    Args:
        path: The access log file.

    Returns:
        The entries, in file order.

    Raises:
        StoreError: If a line is not a JSON object.
    """
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding=JOURNAL_ENCODING)
    except OSError as exc:
        raise StoreError("the held-out access log could not be read", path=str(path)) from exc
    entries: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise StoreError("a held-out access log line is not JSON", path=str(path), line=number) from exc
        if not isinstance(record, dict):
            raise StoreError("a held-out access log line is not an object", path=str(path), line=number)
        entries.append(dict(record))
    return entries
