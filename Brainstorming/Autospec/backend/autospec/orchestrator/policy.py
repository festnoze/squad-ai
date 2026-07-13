"""V3-F6 — Policy Engine d'autonomie (autonomy levels 0-5).

Replaces the scattered binary gates (GOVERNANCE_AUTO, AMENDMENT_AUTO, the
components UI gate…) with ONE deterministic policy: every sensitive action goes
through ``decide(domain, action, state, evidence)`` which answers ALLOW /
REQUIRE_HUMAN / DENY from the project's *effective* autonomy level.

Two-layer model (vision §4):

- **Recommended autonomy** — what the operator dialed in: ``AUTONOMY_LEVEL``
  (global, default 2 = today's human-gated behaviour) plus optional per-domain
  overrides ``AUTONOMY_<DOMAIN>`` (unset = inherit the global level).
- **Effective autonomy** — the engine only ever *downgrades* (never promotes)
  from deterministic distrust signals: anti-cheating guard findings in the
  current iteration, repeated wrong-test arbitrations, a near-exhausted budget,
  a brand-new project. Every downgrade is journaled in ``state.autonomy_log``.

Scoping of the downgrades (golden-compat contract): the distrust signals guard
the SPEC/BACKLOG write domains (``backlog_changes``, ``spec_amendments``) —
the domains whose escalation is human-gated by design. The operational domains
(``memory_writes``, ``delivery``, ``next_feature``) follow the operator's dial
directly: they are ungated-automatic at the default level today, and a global
downgrade on any first-iteration project would silently flip them to
human-gated, changing flag-ON behaviour at default autonomy. The budget signal
additionally applies to ``backlog_changes`` only (creating MORE work while the
budget runs out is the runaway to prevent).

This module is PURE and deterministic: no LLM, no I/O — its only side effect is
appending downgrade traces to ``state.autonomy_log`` (deduplicated, bounded by
the per-iteration signal set).

Soft migration (deprecation path): the legacy binary flags keep working —
``GOVERNANCE_AUTO=1`` is read as an explicit ``AUTONOMY_BACKLOG_CHANGES=5``
order and ``AMENDMENT_AUTO=1`` as ``AUTONOMY_SPEC_AMENDMENTS=5``. Because the
old flags were unconditional, they PIN the effective level (no downgrades):
byte-for-byte compatibility until they are removed.
"""

from __future__ import annotations

import logging
from enum import Enum

from ..config import settings
from ..models import ProjectState

logger = logging.getLogger(__name__)


class Decision(str, Enum):
    ALLOW = "allow"
    REQUIRE_HUMAN = "require_human"
    DENY = "deny"


# The governed domains (plan V3-F6).
DOMAINS = (
    "backlog_changes",   # F3 governance: create/update/enrich/defer/persist/dismiss
    "spec_amendments",   # W5.1: applying a safe spec amendment
    "memory_writes",     # F4: knowledge-base writes (router + governance persist)
    "delivery",          # docker deploy / components setup
    "next_feature",      # auto-spec: picking the next hypothesis unattended
)

# Domain → per-domain settings attribute (None = inherit the global level).
_DOMAIN_SETTING = {
    "backlog_changes": "autonomy_backlog_changes",
    "spec_amendments": "autonomy_spec_amendments",
    "memory_writes": "autonomy_memory_writes",
    "delivery": "autonomy_delivery",
    "next_feature": "autonomy_next_feature",
}

LEVEL_MIN, LEVEL_MAX = 0, 5

# Downgrade thresholds (deterministic, see effective_level).
ARBITRATION_DOWNGRADE_MIN = 2      # ≥ N wrong-test arbitrations this iteration
BUDGET_DOWNGRADE_RATIO = 0.8       # budget consumed beyond this fraction
# Level 4: independent-validation evidence needed for an unattended ALLOW on a
# domain that levels 2-3 keep human-gated (judge verdict or critic score).
VALIDATION_SCORE_MIN = 80

# The domains whose deterministic downgrades apply (module docstring: the
# spec/backlog write domains; operational domains follow the dial directly).
_DOWNGRADED_DOMAINS = ("backlog_changes", "spec_amendments")


def _clamp_level(value, default: int = 2) -> int:
    """Coerce any configured level into 0..5 (invalid → the default)."""
    try:
        level = int(value)
    except (TypeError, ValueError):
        return default
    return max(LEVEL_MIN, min(LEVEL_MAX, level))


def _check_domain(domain: str) -> None:
    if domain not in DOMAINS:
        raise ValueError(f"domaine de politique inconnu : {domain!r}")


def _legacy_pin(domain: str, cfg) -> bool:
    """DEPRECATED compat: is this domain pinned to level 5 by one of the old
    binary flags? ``GOVERNANCE_AUTO=1`` ≡ AUTONOMY_BACKLOG_CHANGES=5 and
    ``AMENDMENT_AUTO=1`` ≡ AUTONOMY_SPEC_AMENDMENTS=5. The old flags were
    unconditional auto-apply orders, so the pin bypasses the downgrades —
    their historical behaviour must stay byte-identical until removal."""
    if domain == "backlog_changes" and bool(getattr(cfg, "governance_auto", False)):
        return True
    if domain == "spec_amendments" and bool(getattr(cfg, "amendment_auto", False)):
        return True
    return False


def recommended_level(domain: str, cfg=None) -> int:
    """The operator-dialed autonomy for one domain: the ``AUTONOMY_<DOMAIN>``
    override when set (legacy compat flags read as 5), else the global
    ``AUTONOMY_LEVEL``. Always clamped to 0..5."""
    cfg = cfg or settings
    _check_domain(domain)
    if _legacy_pin(domain, cfg):
        return LEVEL_MAX
    override = getattr(cfg, _DOMAIN_SETTING[domain], None)
    if override is not None:
        return _clamp_level(override)
    return _clamp_level(getattr(cfg, "autonomy_level", 2))


# ------------------------------------------------------- deterministic signals

def _guard_findings_this_iteration(state: ProjectState) -> bool:
    """Any anti-cheating guard finding (W0.5) on a story of the CURRENT
    iteration — the factory tried to cheat recently, trust less."""
    return any(
        s.guard_findings for s in state.stories if s.iteration == state.iteration
    )


def _arbitration_events(state: ProjectState) -> int:
    """Wrong-test/arbitration events of the current iteration.

    CONSERVATIVE PROXY: arbitration outcomes are recorded on the build monitor
    (``monitor.event("arbitration", …)``) and in an in-memory pipeline counter
    (``_arbitration_count``) — neither lives on ``ProjectState``. The traces
    that DO persist on the state are (a) the ``"arbitration"`` recovery badge
    left on a story whose arbitration confirmed the failure and (b) the
    ``"[arbitrage"`` marker prepended to ``last_error`` on a
    spec-contradiction ruling. We count stories of the current iteration
    bearing either trace: an under-count of total arbitrations (a recovered
    fix_test clears its badge), hence conservative — it can only downgrade
    less often, never more."""
    count = 0
    for s in state.stories:
        if s.iteration != state.iteration:
            continue
        if s.recovery.kind == "arbitration" or "[arbitrage" in (s.last_error or ""):
            count += 1
    return count


def _budget_ratio(state: ProjectState) -> float:
    """The worst consumed fraction across the configured budgets (USD cap and
    token cap — same accounting as the pipeline's ``_budget_reached``).
    0.0 when no budget is configured (0 = no limit)."""
    ratios: list[float] = []
    if state.budget_usd > 0:
        ratios.append(state.usage.cost_usd / state.budget_usd)
    if state.budget_tokens > 0:
        ratios.append(
            (state.usage.input_tokens + state.usage.output_tokens)
            / state.budget_tokens
        )
    return max(ratios, default=0.0)


def _downgrade_reasons(domain: str, state: ProjectState) -> list[str]:
    """The deterministic distrust signals firing for this domain (each −1)."""
    reasons: list[str] = []
    if domain in _DOWNGRADED_DOMAINS:
        if _guard_findings_this_iteration(state):
            reasons.append("guard findings sur l'itération courante")
        if _arbitration_events(state) >= ARBITRATION_DOWNGRADE_MIN:
            reasons.append(
                f"≥ {ARBITRATION_DOWNGRADE_MIN} arbitrages wrong-test sur l'itération"
            )
        if state.iteration <= 1:
            reasons.append("première itération du projet")
    if domain == "backlog_changes" and _budget_ratio(state) > BUDGET_DOWNGRADE_RATIO:
        reasons.append(
            f"budget consommé > {int(BUDGET_DOWNGRADE_RATIO * 100)} %"
        )
    return reasons


def _log_downgrade(
    state: ProjectState, domain: str, reason: str, from_level: int, to_level: int
) -> None:
    """Journal one downgrade in ``state.autonomy_log`` (traceability). The
    entry is deduplicated — ``decide`` may run many times per iteration and the
    log must stay bounded by the signal set, not the call count."""
    entry = f"iter {state.iteration} [{domain}] {reason} : {from_level}→{to_level}"
    if entry not in state.autonomy_log:
        state.autonomy_log.append(entry)


def effective_level(domain: str, state: ProjectState, cfg=None) -> int:
    """Recommended level minus the deterministic downgrades — NEVER promoted
    above the recommended level, floored at 0. A legacy compat pin
    (GOVERNANCE_AUTO / AMENDMENT_AUTO) bypasses the downgrades (see module
    docstring). Downgrades are journaled in ``state.autonomy_log``."""
    cfg = cfg or settings
    _check_domain(domain)
    if _legacy_pin(domain, cfg):
        return LEVEL_MAX
    level = recommended_level(domain, cfg)
    for reason in _downgrade_reasons(domain, state):
        if level <= LEVEL_MIN:
            break
        _log_downgrade(state, domain, reason, level, level - 1)
        level -= 1
    return level


# ---------------------------------------------------------- level → decision

def _evidence_validated(evidence: dict) -> bool:
    """Level 4: does the evidence carry an INDEPENDENT validation (a judge/
    arbiter verdict, or a critic score above the bar)?"""
    if bool(evidence.get("judge_validated")):
        return True
    try:
        return float(evidence.get("critic_score", 0)) >= VALIDATION_SCORE_MIN
    except (TypeError, ValueError):
        return False


def _base_decision(domain: str, action: str) -> Decision:
    """The levels 2-3 mapping — today's default behaviour: backlog and spec
    changes are human-gated; memory writes, docker deploy and next-feature
    selection run unattended; the components setup keeps its human UI gate."""
    if domain in ("backlog_changes", "spec_amendments"):
        return Decision.REQUIRE_HUMAN
    if domain == "delivery" and action == "setup_components":
        return Decision.REQUIRE_HUMAN
    return Decision.ALLOW  # memory_writes, delivery:docker_deploy, next_feature


def decide(
    domain: str,
    action: str,
    state: ProjectState,
    evidence: dict | None = None,
    cfg=None,
) -> Decision:
    """THE policy entry point — pure and deterministic (no LLM, no I/O).

    Order of authority:

    1. **Hard DENY rules** (never overridden by any level or legacy flag):
       a fully exhausted budget denies ``backlog_changes`` *create* actions —
       a factory out of budget must not grow its own backlog.
    2. **Effective level mapping**:
       - 0-1 → REQUIRE_HUMAN everywhere;
       - 2-3 → today's behaviour (see ``_base_decision``);
       - 4   → everything 2-3 allows, plus ALLOW on the human-gated actions
               when the evidence carries an independent validation
               (``judge_validated`` / ``critic_score`` ≥ threshold),
               else REQUIRE_HUMAN;
       - 5   → ALLOW.
    """
    cfg = cfg or settings
    evidence = evidence or {}
    _check_domain(domain)

    # 1. Hard DENY rules (minimal by design, plan V3-F6).
    if (
        domain == "backlog_changes"
        and action.startswith("create")
        and _budget_ratio(state) >= 1.0
    ):
        return Decision.DENY

    # 2. Effective autonomy → decision.
    level = effective_level(domain, state, cfg)
    if level <= 1:
        return Decision.REQUIRE_HUMAN
    if level >= LEVEL_MAX:
        return Decision.ALLOW
    base = _base_decision(domain, action)
    if level == 4 and base is Decision.REQUIRE_HUMAN:
        return Decision.ALLOW if _evidence_validated(evidence) else Decision.REQUIRE_HUMAN
    return base
