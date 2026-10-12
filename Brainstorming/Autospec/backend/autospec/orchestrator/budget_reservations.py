"""Optional, durable USD reservations; disabled unless a provider is proven bounded.

This does not turn a CLI's estimated-budget flag into a hard billing guarantee.
Only a factory-reviewed, hash-pinned provider receipt can enable admission. An
unknown cost keeps its envelope reserved and blocks new calls. Actual overshoot
and cap reductions are recorded honestly, never clipped to make a ledger green.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
import stat
import threading
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

from ..agents.runner import active_budget_usd
from .dependencies import atomic_json, file_lock


class BudgetReservationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _usd(value) -> Decimal:
    try:
        if isinstance(value, bool):
            raise ValueError()
        text = str(value)
        if len(text) > 500:
            raise ValueError()
        amount = Decimal(text)
        if not amount.is_finite() or amount < 0 or abs(amount.adjusted()) > 400:
            raise ValueError()
        return amount
    except (ValueError, InvalidOperation):
        raise BudgetReservationError("INVALID_USD", "Finite nonnegative USD required") from None


def _text(amount: Decimal) -> str:
    return format(amount, "f")


def _json_file(path: Path) -> dict:
    path = Path(path).absolute()
    info = path.lstat()
    if path.resolve() != path or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 2_000_000:
        raise BudgetReservationError("UNSAFE_LEDGER", "Factory record must be a bounded unaliased regular file")
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise BudgetReservationError("INVALID_LEDGER", "Factory record must be an object")
    return result


@dataclass(frozen=True)
class ProviderBudgetProof:
    """Factory-owned reviewed receipt, not a provider/model self-assertion.

    Receipt version1: provider, currency=USD, bound_kind=hard_usd,
    whole_logical_call/all_billable_costs/enforced_before_overshoot=True,
    exact_usd_transport=active_budget_usd, reviewed_by nonempty. expected hash
    must come from a trusted registry outside the producer writable root.
    """
    provider: str
    evidence_path: Path
    evidence_sha256: str

    def verify(self, producer_root: Path | None = None) -> None:
        path = Path(self.evidence_path).absolute()
        if producer_root is not None and path.resolve().is_relative_to(producer_root.resolve()):
            raise BudgetReservationError("PROVIDER_UNBOUNDED", "Provider proof cannot be producer-owned")
        try:
            receipt = _json_file(path)
            data = path.read_bytes()
        except (OSError, ValueError, TypeError) as exc:
            raise BudgetReservationError("PROVIDER_UNBOUNDED", "Provider receipt unavailable or invalid") from exc
        if hashlib.sha256(data).hexdigest() != self.evidence_sha256 or json.loads(data) != receipt:
            raise BudgetReservationError("PROVIDER_UNBOUNDED", "Provider proof identity changed")
        if (receipt.get("version") != 1 or receipt.get("provider") != self.provider or
            receipt.get("currency") != "USD" or receipt.get("bound_kind") != "hard_usd" or
            any(receipt.get(key) is not True for key in
                ("whole_logical_call", "all_billable_costs", "enforced_before_overshoot")) or
            receipt.get("exact_usd_transport") != "active_budget_usd" or
            not isinstance(receipt.get("reviewed_by"), str) or not receipt["reviewed_by"].strip()):
            raise BudgetReservationError("PROVIDER_UNBOUNDED", "No reviewed hard whole-call USD ceiling")


@dataclass(frozen=True)
class Reservation:
    ticket: str
    call_id: str


@dataclass(frozen=True)
class ProviderEnvelope:
    ticket: str
    provider: str
    usd_limit: str
    proof_sha256: str
    _bind_lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)
    _used: bool = field(default=False, repr=False, compare=False)

    @property
    def digest(self) -> str:
        return hashlib.sha256(json.dumps({"ticket": self.ticket, "provider": self.provider,
            "usd_limit": self.usd_limit, "proof_sha256": self.proof_sha256}, sort_keys=True).encode()).hexdigest()

    @contextlib.contextmanager
    def bind(self):
        """Exact existing runner ContextVar transport, restored on cancellation.

        Arbitrary Decimal->float rounding is refused before dispatch. Runner
        must pass str(active_budget_usd) unchanged as its native USD envelope.
        """
        value = float(self.usd_limit)
        if not math.isfinite(value) or Decimal(str(value)) != _usd(self.usd_limit):
            raise BudgetReservationError("INEXACT_ENVELOPE", "Existing provider transport cannot represent this envelope exactly")
        with self._bind_lock:
            if self._used:
                raise BudgetReservationError("DUPLICATE_DISPATCH", "One reservation cannot launch a second provider call")
            object.__setattr__(self, "_used", True)
        token = active_budget_usd.set(value)
        try:
            yield self
        finally:
            active_budget_usd.reset(token)


class BudgetReservations:
    """Cross-thread/process atomic reservations, persisted BEFORE admission.

    Cap updates affect new admissions only. A cap below already committed spend
    creates visible debt and blocks admission; paid/in-flight amounts remain.
    Caller serializes or refuses when DISABLED/PROVIDER_UNBOUNDED/TOKEN_UNBOUNDED.
    Capacity waiters should wake after reconcile/update_cap, not busy-spin.
    """
    def __init__(self, cap_usd, *, journal: Path | None = None, budget_id: str = "",
                 enabled: bool = False, initial_cost_usd=None, historical_unreported: int = 0,
                 producer_root: Path | None = None):
        self.enabled = enabled
        self.journal = Path(journal).absolute() if journal is not None else None
        self.producer_root = Path(producer_root).resolve() if producer_root is not None else None
        self.lock = threading.RLock()
        self.budget_id = budget_id
        self.storage_failed = False
        if type(enabled) is not bool:
            raise BudgetReservationError("INVALID_LEDGER", "Explicit boolean feature flag required")
        if type(historical_unreported) is not int or historical_unreported < 0:
            raise BudgetReservationError("INVALID_LEDGER", "Invalid historical unreported count")
        self.state = {"version": 1, "budget_id": budget_id, "cap_usd": _text(_usd(cap_usd)),
                      "initial_cost_usd": _text(_usd(initial_cost_usd if initial_cost_usd is not None else 0)),
                      "historical_unreported": historical_unreported, "entries": {}, "breaches": [],
                      "cap_lowered_inflight": False}
        if enabled and (self.journal is None or not budget_id):
            raise BudgetReservationError("DURABILITY_REQUIRED", "Enabled reservations need an external journal and identity")
        if self.journal is not None:
            if self.producer_root is not None and self.journal.resolve().is_relative_to(self.producer_root):
                raise BudgetReservationError("UNSAFE_LEDGER", "Budget journal must be outside producer root")
            if self.journal.parent.resolve() != self.journal.parent:
                raise BudgetReservationError("UNSAFE_LEDGER", "Budget journal parent is aliased")
            with self._transaction():
                if _usd(self.state["cap_usd"]) != _usd(cap_usd):
                    raise BudgetReservationError("CAP_UPDATE_REQUIRED", "Restored cap differs; explicitly update the existing ledger")
                if initial_cost_usd is not None and _usd(self.state["initial_cost_usd"]) != _usd(initial_cost_usd):
                    raise BudgetReservationError("HISTORY_UPDATE_REQUIRED", "Existing recorded history cannot be replaced by a different initial seed")
                for entry in self.state["entries"].values():
                    if entry["status"] != "reconciled":
                        entry["status"] = "unreported"  # restart/crash: no lost in-flight charge

    @contextlib.contextmanager
    def _transaction(self):
        with self.lock:
            guard = file_lock(self.journal.with_suffix(self.journal.suffix + ".lock"), timeout=10) if self.journal else contextlib.nullcontext()
            with guard:
                if self.journal and self.journal.exists():
                    saved = _json_file(self.journal)
                    if saved.get("version") != 1 or saved.get("budget_id") != self.budget_id:
                        raise BudgetReservationError("INVALID_LEDGER", "Budget journal identity/version mismatch")
                    self.state = saved
                yield
                if self.journal:
                    try:
                        atomic_json(self.journal, self.state)
                    except BaseException:
                        self.storage_failed = True
                        raise

    def _summary(self) -> dict:
        # Preserve even subnormal float-sized reported costs. Bounded Decimal
        # exponents + sufficient precision avoid silently rounding an overshoot.
        with localcontext() as precision:
            precision.prec = 2048
            return self._summary_exact()

    def _summary_exact(self) -> dict:
        spent = _usd(self.state["initial_cost_usd"])
        reserved = Decimal(0)
        unknown = self.state["historical_unreported"]
        overshoot = Decimal(0)
        for entry in self.state["entries"].values():
            cost, allowance = _usd(entry["cost_usd"]), _usd(entry["allowance_usd"])
            spent += cost
            overshoot += max(Decimal(0), cost - allowance)
            if entry["status"] != "reconciled":
                reserved += max(Decimal(0), allowance - cost)
            unknown += int(entry["status"] == "unreported")
        cap = _usd(self.state["cap_usd"])
        reasons = []
        if unknown:
            reasons.append("COST_UNREPORTED")
        if self.storage_failed:
            reasons.append("STORAGE_FAILED")
        if overshoot or self.state["breaches"]:
            reasons.append("PROVIDER_BOUND_BREACH")
        debt = max(Decimal(0), spent + reserved - cap)
        if debt:
            reasons.append("CAP_DEBT")
        if self.state.get("cap_lowered_inflight") and any(entry["status"] != "reconciled" for entry in self.state["entries"].values()):
            reasons.append("CAP_CHANGED_IN_FLIGHT")
        return {"version": 1, "enabled": self.enabled, "budget_id": self.budget_id,
                "cap_usd": _text(cap), "recorded_usd": _text(spent), "reserved_usd": _text(reserved),
                "available_usd": _text(max(Decimal(0), cap - spent - reserved)),
                "cap_debt_usd": _text(debt), "overshoot_usd": _text(overshoot),
                "unreported_calls": unknown, "blocked_reasons": reasons,
                "entries": json.loads(json.dumps(self.state["entries"]))}

    def snapshot(self) -> dict:
        if self.storage_failed:
            with self.lock:
                return self._summary()  # don't reload older disk totals over newer known spend
        with self._transaction():
            return self._summary()

    def update_cap(self, cap_usd) -> dict:
        with self._transaction():
            amount = _usd(cap_usd)
            if amount < _usd(self.state["cap_usd"]) and any(entry["status"] != "reconciled" for entry in self.state["entries"].values()):
                self.state["cap_lowered_inflight"] = True
            self.state["cap_usd"] = _text(amount)
            return self._summary()

    def acquire(self, call_id: str, usd, provider: ProviderBudgetProof, *, token_cap: int | None = None) -> Reservation:
        if not self.enabled:
            raise BudgetReservationError("DISABLED", "Concurrent reservations are OFF by default")
        if self.storage_failed:
            raise BudgetReservationError("STORAGE_FAILED", "Known usage could not be persisted; no further admission")
        if token_cap is not None:
            # This USD optimization does not remove the existing serialized
            # token guard. No total-token hard-bound transport exists here.
            raise BudgetReservationError("TOKEN_UNBOUNDED", "Active token budget cannot enter the USD-only concurrent lane")
        if not isinstance(call_id, str) or not call_id.strip() or len(call_id) > 256:
            raise BudgetReservationError("INVALID_CALL", "Unique logical call identity required")
        amount = _usd(usd)
        if amount <= 0:
            raise BudgetReservationError("INVALID_USD", "Positive per-call envelope required")
        provider.verify(self.producer_root)
        # Fail before persisting a reservation which cannot reach the runner.
        transported = float(amount)
        if not math.isfinite(transported) or Decimal(str(transported)) != amount:
            raise BudgetReservationError("INEXACT_ENVELOPE", "Exact native envelope transport unavailable")
        with self._transaction():
            summary = self._summary()
            if any(entry["call_id"] == call_id for entry in self.state["entries"].values()):
                raise BudgetReservationError("DUPLICATE_CALL", "A retry cannot dispatch the same logical call twice")
            if summary["blocked_reasons"]:
                raise BudgetReservationError(summary["blocked_reasons"][0], "Unresolved usage or breached bound blocks all admission")
            if amount > _usd(summary["available_usd"]):
                raise BudgetReservationError("BUDGET_RESERVED", "Recorded consumption plus reservations would exceed cap")
            ticket = uuid.uuid4().hex
            self.state["entries"][ticket] = {"call_id": call_id, "provider": provider.provider,
                "proof_path": str(Path(provider.evidence_path).absolute()), "proof_sha256": provider.evidence_sha256,
                "allowance_usd": str(transported), "admission_cap_usd": self.state["cap_usd"],
                "cost_usd": "0", "status": "reserved", "reports": []}
            return Reservation(ticket, call_id)

    def _entry(self, reservation: Reservation) -> dict:
        entry = self.state["entries"].get(reservation.ticket)
        if entry is None or entry["call_id"] != reservation.call_id:
            raise BudgetReservationError("UNKNOWN_RESERVATION", "Reservation identity does not belong to this ledger")
        return entry

    def envelope(self, reservation: Reservation) -> ProviderEnvelope:
        with self._transaction():
            entry = self._entry(reservation)
            if entry["status"] != "reserved":
                raise BudgetReservationError("INACTIVE_RESERVATION", "No redispatch after cancellation/result")
            ProviderBudgetProof(entry["provider"], Path(entry["proof_path"]), entry["proof_sha256"]).verify(self.producer_root)
            entry["status"] = "issued"  # durable single-dispatch marker
            return ProviderEnvelope(reservation.ticket, entry["provider"], entry["allowance_usd"], entry["proof_sha256"])

    def reconcile(self, reservation: Reservation, cost_usd, *, complete: bool = True) -> dict:
        try:
            cost = _usd(cost_usd)
        except BudgetReservationError:
            self.cancel(reservation)
            raise
        if type(complete) is not bool:
            self.cancel(reservation)
            raise BudgetReservationError("INVALID_USAGE", "Explicit complete/incomplete usage required")
        with self._transaction():
            entry = self._entry(reservation)
            previous = _usd(entry["cost_usd"])
            if cost < previous or entry["status"] == "reconciled" and cost != previous:
                self.state["breaches"].append({"ticket": reservation.ticket, "previous_usd": _text(previous),
                                                "conflicting_usd": _text(cost)})
            # Cumulative provider totals, never additive duplicate receipts.
            # All conflicting totals remain auditable; no downward correction
            # may erase an overshoot or previously reported paid consumption.
            entry["reports"].append({"cost_usd": _text(cost), "complete": complete})
            entry["cost_usd"] = _text(max(previous, cost))
            if entry["status"] != "reconciled":
                entry["status"] = "reconciled" if complete else "unreported"
            return self._summary()

    def cancel(self, reservation: Reservation, *, cost_usd=None, complete: bool = False) -> dict:
        """Release only a known FINAL cost; unknown/partial stays reserved.

        Before provider dispatch, cancel(cost_usd=0,complete=True) is valid.
        Cancellation/timeout after launch is NOT evidence of a zero/free call.
        A later complete reconcile can resolve an unknown canceled call.
        """
        if cost_usd is not None:
            return self.reconcile(reservation, cost_usd, complete=complete)
        with self._transaction():
            entry = self._entry(reservation)
            if entry["status"] != "reconciled":
                entry["status"] = "unreported"
            return self._summary()
