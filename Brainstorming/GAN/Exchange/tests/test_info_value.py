"""FR-5.3.1: private signals have measurable value, and the noise control proves it.

The requirement is "un agent bayesien scripte exploitant ses signaux doit battre
un agent aleatoire". Taken alone that claim is worthless as a test of the
information engine: a Brier score punishes confident nonsense, so an agent that
declares the public prior at every tick already beats a uniformly random one by
a wide margin, and it would keep beating it if every signal this package emits
were replaced by white noise. A green "bayesian beats random" therefore proves
nothing about :mod:`pxe.info`.

This file measures the claim on three baselines and adds the control that gives
it teeth:

* ``random`` declares a uniformly drawn probability. Its expected Brier is
  exactly ``1/3`` whatever the world does, which makes it the FR-5.3.1
  reference.
* ``prior`` declares the public opening prior of FR-5.2.4 at every tick and
  reads no signal. It is the *information free* baseline: whatever separates the
  Bayesian agent from this one came from the signal stream and from nowhere
  else.
* ``bayes`` runs a Kalman style update of the latent value from its own private
  signals, inverting :func:`pxe.info.noise.precision_ppm_for_sigma` to recover
  the observation variance the engine published.
* ``bayes_on_noise`` is the same agent fed the same number of signals, with the
  same declared precisions, whose values were redrawn from
  :func:`pxe.info.noise.pure_noise_latent_milli`. It is the control: if it also
  beat ``prior``, the measured edge would live in the agent's machinery rather
  than in the information, and this file would be testing arithmetic.

Every draw is seeded (worlds ``SEED_BASE .. SEED_BASE + N_MATCHES - 1``), the
primary statistic is a paired z test on the per match Brier difference with an
exact sign test reported beside it, and the tolerance is stated at every
assertion. Marked ``statistical`` and ``slow`` per CONTRACTS section 10.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pytest

from pxe.info.engine import InfoEngine
from pxe.info.noise import (
    latent_milli_from_probability_milli,
    pure_noise_latent_milli,
    sigma_milli_for_precision,
)
from pxe.info.profiles import build_profile
from pxe.rng import RngTree, randint
from pxe.types import (
    PPM_ONE,
    InfoProfileKind,
    Outcome,
    Signal,
    SignalKind,
    brier_term_ppm,
    make_agent_id,
    round_half_up,
    sorted_ids,
)
from pxe.world.generator import generate_world
from pxe.world.latent import milli_from_probability_ppm, probability_ppm_from_milli

pytestmark = [pytest.mark.statistical, pytest.mark.slow]

#: First world seed and the match count. FR-5.3.1 says "1 000 matchs" and that
#: is taken literally: the effect the engine has to produce is real but small
#: (the latent process mean reverts, so an observation at tick ``t`` says little
#: about tick ``T``), which makes the sample size part of the requirement rather
#: than a knob. Worlds are ``SEED_BASE .. SEED_BASE + N_MATCHES - 1``.
SEED_BASE = 900_000
N_MATCHES = 1_000
TICKS_TOTAL = 24
N_MARKETS = 4

#: Latent drift per tick, in ``_milli``, and the pull back toward the centre, in
#: ppm of the remaining distance. These are the two numbers the world's templates
#: draw their paths with; the agent knows the *shape* of the process (an
#: Ornstein-Uhlenbeck style mean reverting walk) and not the hidden value, which
#: is exactly the position a scripted agent is in.
DRIFT_SIGMA_MILLI = 130
MEAN_REVERSION_PPM = 80_000

#: Prior spread of the belief, in latent ``_milli``: the stationary spread of
#: that process, ``sigma / sqrt(1 - (1 - kappa)^2)``. Getting this from the
#: process instead of picking a round number is what makes the belief agree with
#: the prior when it has heard nothing yet, which is the only way the "signals
#: paid" duel measures the signals and not a lucky prior width.
PRIOR_SIGMA_MILLI = 332

#: How a coarse signal shape is turned into an observation. A ``DIRECTION``
#: carries one bit and a ``THRESHOLD`` one bound, so both are entered as weak
#: observations rather than being thrown away.
DIRECTION_PULL_MILLI = 250
DIRECTION_SIGMA_MILLI = 700
THRESHOLD_MARGIN_MILLI = 150
THRESHOLD_SIGMA_MILLI = 500

_PROBABILITY_MILLI_ONE = 1_000


# ---------------------------------------------------------------------------
# The scripted Bayesian belief
# ---------------------------------------------------------------------------
#: Five point Gauss-Hermite rule for ``E[f(mu + sigma Z)]`` with ``Z`` standard
#: normal. The weights sum to one by construction. It is here because the Brier
#: score wants ``E[p(latent)]`` and not ``p(E[latent])``: with a wide belief the
#: two differ by tens of thousands of ppm, and using the second is how a filter
#: ends up more confident than its own information justifies.
_GAUSS_HERMITE: tuple[tuple[float, float], ...] = (
    (-2.856970013872805, 0.011257411327720688),
    (-1.355626179974266, 0.2220759220056126),
    (0.0, 0.5333333333333333),
    (1.355626179974266, 0.2220759220056126),
    (2.856970013872805, 0.011257411327720688),
)

_KAPPA = MEAN_REVERSION_PPM / PPM_ONE
_DECAY = 1.0 - _KAPPA


def _drift_sum(steps: int) -> float:
    """Return ``sum(_DECAY ** (2 * i) for i in range(steps))`` in closed form.

    Args:
        steps: Number of ticks, ``>= 0``.

    Returns:
        The geometric sum. Closed form and not a loop because this is the inner
        expression of a thousand match sweep.
    """
    if steps <= 0:
        return 0.0
    ratio = _DECAY**2
    return (1.0 - ratio**steps) / (1.0 - ratio)


@dataclass
class Belief:
    """A Gaussian belief over one market's latent value, in ``_milli``.

    The process is mean reverting, so the belief is too: without the pull toward
    ``centre_milli`` a stale observation keeps its full weight forever, the agent
    stays confident about a latent value that has long since drifted back, and it
    scores *worse* than declaring the public prior. That failure mode is not
    hypothetical, it is what the first draft of this file measured.
    """

    centre_milli: float
    mean_milli: float
    variance: float

    def drift(self) -> None:
        """Advance one tick of the mean reverting latent process."""
        self.mean_milli = self.centre_milli + _DECAY * (self.mean_milli - self.centre_milli)
        self.variance = _DECAY**2 * self.variance + float(DRIFT_SIGMA_MILLI) ** 2

    def observe(self, value_milli: float, sigma_milli: float) -> None:
        """Fold in one observation of the latent value.

        Args:
            value_milli: Observed latent value.
            sigma_milli: Standard deviation of the observation error, ``> 0``.
        """
        observation_variance = max(1.0, sigma_milli) ** 2
        gain = self.variance / (self.variance + observation_variance)
        self.mean_milli += gain * (value_milli - self.mean_milli)
        self.variance *= 1.0 - gain

    def p_yes_ppm(self, *, steps: int) -> int:
        """Forecast the probability of YES ``steps`` ticks ahead.

        Args:
            steps: Ticks from now to the resolution tick, ``>= 0``. The outcome
                is drawn from the latent value *there*, not from today's, so a
                forecast that ignored the remaining drift would be systematically
                overconfident.

        Returns:
            The probability in parts per million.
        """
        decay = _DECAY**steps
        mean = self.centre_milli + decay * (self.mean_milli - self.centre_milli)
        variance = decay**2 * self.variance + float(DRIFT_SIGMA_MILLI) ** 2 * _drift_sum(steps)
        sigma = math.sqrt(max(1.0, variance))
        total = 0.0
        for node, weight in _GAUSS_HERMITE:
            total += weight * probability_ppm_from_milli(round_half_up(mean + sigma * node))
        return min(PPM_ONE, max(0, round_half_up(total)))


def observation_of(signal: Signal) -> tuple[float, float]:
    """Translate one signal into a ``(latent value, sigma)`` observation.

    Args:
        signal: The delivered signal.

    Returns:
        The observed latent value in ``_milli`` and the standard deviation the
        agent should attach to it.
    """
    sigma = float(max(1, sigma_milli_for_precision(max(1, signal.precision_ppm))))
    if signal.kind is SignalKind.POINT_ESTIMATE:
        return float(latent_milli_from_probability_milli(signal.value_milli)), sigma
    if signal.kind is SignalKind.DIRECTION:
        pull = DIRECTION_PULL_MILLI if signal.value_milli > 0 else -DIRECTION_PULL_MILLI
        return float(pull), float(DIRECTION_SIGMA_MILLI)
    level = latent_milli_from_probability_milli(min(_PROBABILITY_MILLI_ONE, abs(signal.value_milli)))
    margin = THRESHOLD_MARGIN_MILLI if signal.value_milli > 0 else -THRESHOLD_MARGIN_MILLI
    return float(level + margin), float(THRESHOLD_SIGMA_MILLI)


# ---------------------------------------------------------------------------
# One match, four scorers
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MatchScores:
    """Mean Brier score in ppm of the four scorers over one world."""

    random: int
    prior: int
    bayes: int
    bayes_on_noise: int
    n_terms: int
    n_signals: int


def _mean_ppm(total: int, count: int) -> int:
    """Return ``total / count`` rounded half up, or ``0`` when there is nothing."""
    if count == 0:
        return 0
    return (2 * total + count) // (2 * count)


def play(seed: int) -> MatchScores:
    """Score the four baselines on the world of ``seed``.

    The Brier terms follow PRD section 7.2 as CONTRACTS section 5.0 reads it: a
    market with ``resolution_tick == r`` contributes one term per tick from 1 to
    ``r`` inclusive.

    Args:
        seed: World seed.

    Returns:
        The four mean scores plus the counts the anti-vacuous assertions need.
    """
    world = generate_world(template_id="election", seed=seed, ticks_total=TICKS_TOTAL, n_markets=N_MARKETS)
    market_ids = world.market_ids()
    agent_id = make_agent_id(1)
    profiles = {agent_id: build_profile(InfoProfileKind.GENERALIST, market_ids=market_ids)}
    engine = InfoEngine(
        world=world,
        profiles=profiles,
        rng=RngTree(seed).child("info"),
        ticks_total=TICKS_TOTAL,
    )
    tree = RngTree(seed)
    random_rng = tree.fresh_substream("test.scratch")
    control_rng = tree.fresh_substream("test.control")

    spec_of = {market.market_id: market for market in world.scenario.markets}
    prior_ppm = {mid: min(PPM_ONE - 1, max(1, spec_of[mid].prior_price * 10_000)) for mid in market_ids}
    centre_of = {mid: float(milli_from_probability_ppm(prior_ppm[mid])) for mid in market_ids}
    beliefs = {mid: Belief(centre_of[mid], centre_of[mid], float(PRIOR_SIGMA_MILLI) ** 2) for mid in market_ids}
    control_beliefs = {mid: Belief(centre_of[mid], centre_of[mid], float(PRIOR_SIGMA_MILLI) ** 2) for mid in market_ids}
    outcomes: dict[str, Outcome] = {mid: world.outcome(mid) for mid in market_ids}

    totals = {"random": 0, "prior": 0, "bayes": 0, "bayes_on_noise": 0}
    n_terms = 0
    n_signals = 0
    for tick in range(1, TICKS_TOTAL + 1):
        for mid in market_ids:
            beliefs[mid].drift()
            control_beliefs[mid].drift()
        for signal in engine.signals_for_tick(tick):
            if signal.market_id not in prior_ppm:
                continue
            n_signals += 1
            value, sigma = observation_of(signal)
            beliefs[signal.market_id].observe(value, sigma)
            # The control keeps the shape, the count and the declared precision
            # of every signal and replaces only its value by pure noise.
            control_beliefs[signal.market_id].observe(float(pure_noise_latent_milli(control_rng)), sigma)
        for mid in sorted_ids(list(market_ids)):
            if tick > spec_of[mid].resolution_tick:
                continue
            outcome = outcomes[mid]
            n_terms += 1
            totals["random"] += brier_term_ppm(randint(random_rng, 0, PPM_ONE), outcome)
            totals["prior"] += brier_term_ppm(prior_ppm[mid], outcome)
            steps = spec_of[mid].resolution_tick - tick
            totals["bayes"] += brier_term_ppm(beliefs[mid].p_yes_ppm(steps=steps), outcome)
            totals["bayes_on_noise"] += brier_term_ppm(control_beliefs[mid].p_yes_ppm(steps=steps), outcome)
    return MatchScores(
        random=_mean_ppm(totals["random"], n_terms),
        prior=_mean_ppm(totals["prior"], n_terms),
        bayes=_mean_ppm(totals["bayes"], n_terms),
        bayes_on_noise=_mean_ppm(totals["bayes_on_noise"], n_terms),
        n_terms=n_terms,
        n_signals=n_signals,
    )


_CACHE: list[MatchScores] = []


def scores() -> list[MatchScores]:
    """Score every match once and memoise the result for the whole module."""
    if not _CACHE:
        _CACHE.extend(play(SEED_BASE + index) for index in range(N_MATCHES))
    return _CACHE


# ---------------------------------------------------------------------------
# The statistic
# ---------------------------------------------------------------------------
def sign_test_p_value(wins: int, losses: int) -> float:
    """Two-sided exact sign test.

    Args:
        wins: Matches where the challenger scored strictly better.
        losses: Matches where it scored strictly worse. Ties are discarded, as
            the sign test requires.

    Returns:
        The two-sided p-value under ``H0: p = 1/2``. ``1.0`` when there is no
        decided match at all.
    """
    n = wins + losses
    if n == 0:
        return 1.0
    extreme = max(wins, losses)
    tail = sum(math.comb(n, k) for k in range(extreme, n + 1))
    return min(1.0, 2.0 * tail / float(2**n))


@dataclass(frozen=True)
class Duel:
    """The outcome of comparing two scorers over every match.

    Attributes:
        z: Paired z statistic of ``incumbent - challenger`` (positive means the
            challenger scored better). This is the primary statistic: the sign
            test discards the size of every difference and is markedly less
            powerful on an effect this small.
        mean_gain_ppm: Mean Brier advantage of the challenger, in ppm.
        wins: Matches the challenger won.
        losses: Matches it lost.
        sign_p: Two-sided sign test p-value, reported alongside as a
            distribution free cross check.
    """

    z: float
    mean_gain_ppm: float
    wins: int
    losses: int
    sign_p: float

    def __str__(self) -> str:
        """Return a one line summary for an assertion message."""
        return (
            f"z={self.z:.2f}, mean gain {self.mean_gain_ppm:.0f} ppm, "
            f"{self.wins} wins / {self.losses} losses, sign p={self.sign_p:.3g}"
        )


def duel(challenger: str, incumbent: str) -> Duel:
    """Compare two scorers over every match (a lower Brier score wins).

    Args:
        challenger: Attribute name of the challenger on :class:`MatchScores`.
        incumbent: Attribute name of the incumbent.

    Returns:
        The :class:`Duel` summary.
    """
    rows = scores()
    diffs = [float(getattr(row, incumbent) - getattr(row, challenger)) for row in rows]
    n = len(diffs)
    mean = sum(diffs) / n
    variance = sum((value - mean) ** 2 for value in diffs) / (n - 1)
    standard_error = math.sqrt(variance / n) if variance > 0.0 else 0.0
    z = 0.0 if standard_error == 0.0 else mean / standard_error
    wins = sum(1 for value in diffs if value > 0.0)
    losses = sum(1 for value in diffs if value < 0.0)
    return Duel(z=z, mean_gain_ppm=mean, wins=wins, losses=losses, sign_p=sign_test_p_value(wins, losses))


def mean_of(field: str) -> int:
    """Return the mean of one scorer's Brier score in ppm over every match."""
    rows = scores()
    return _mean_ppm(sum(getattr(row, field) for row in rows), len(rows))


# ---------------------------------------------------------------------------
# The tests
# ---------------------------------------------------------------------------
def test_information_has_value():
    """FR-5.3.1, with the pure noise control that makes the claim mean something."""
    rows = scores()
    # Anti-vacuous first (CONTRACTS section 10): no signals, no claim.
    assert len(rows) == N_MATCHES
    assert all(row.n_terms > 0 for row in rows), "a match produced no Brier term"
    total_signals = sum(row.n_signals for row in rows)
    assert total_signals >= 4 * N_MATCHES, f"only {total_signals} signals over {N_MATCHES} matches: vacuous"

    # 1. The literal FR-5.3.1 claim. Tolerance: z > 10 and an exact sign test
    #    under 1e-6. The random scorer's expected Brier is exactly 1/3 whatever
    #    the world does, so this margin is wide by construction.
    versus_random = duel("bayes", "random")
    assert versus_random.z > 10.0, f"the Bayesian agent did not beat the random one: {versus_random}"
    assert versus_random.sign_p < 1e-6, f"not significant: {versus_random}"
    assert mean_of("bayes") < mean_of("random")

    # 2. Where the edge comes from. The public prior of FR-5.2.4 is free
    #    information, so beating the random scorer proves nothing on its own;
    #    beating the prior-only scorer is what says the *signals* paid.
    #    Tolerance: z > 3.5 (two-sided p under 5e-4), with the sign test under
    #    0.05 as a distribution free cross check.
    versus_prior = duel("bayes", "prior")
    assert versus_prior.z > 3.5, f"reading the signals did not pay: {versus_prior}"
    assert versus_prior.sign_p < 0.05, f"the sign test disagrees with the z test: {versus_prior}"
    assert mean_of("bayes") < mean_of("prior")

    # 3. The control. Replace the signal values by pure noise, keep everything
    #    else (count, shape, declared precision, the agent itself), and the edge
    #    of assertion 2 must disappear. Tolerance: z < 1.96, that is no
    #    improvement detectable at the 5 percent level over the information free
    #    baseline. Anything above that would mean assertion 2 was measuring the
    #    filter's arithmetic instead of the information.
    control = duel("bayes_on_noise", "prior")
    assert control.z < 1.96, (
        "pure noise signals still beat the prior-only baseline, so assertion 2 "
        f"was not measuring the information: {control}"
    )
    assert mean_of("bayes") < mean_of("bayes_on_noise"), "the real signal stream was no better than white noise"


def test_pure_noise_signals_have_no_value():
    """The control of :func:`test_information_has_value`, asserted on its own.

    Kept as a separate test so a regression in the noise model is reported as
    "noise became informative" rather than hidden inside the FR-5.3.1 failure.
    Tolerance: the paired z statistic against the information free baseline must
    stay under 1.96.
    """
    rows = scores()
    assert rows, "vacuous"
    assert sum(row.n_signals for row in rows) > 0, "vacuous: no signal reached the control agent"
    control = duel("bayes_on_noise", "prior")
    assert control.z < 1.96, f"white noise beat the information free baseline: {control}"


def test_the_random_scorer_sits_at_one_third():
    """Sanity check on the FR-5.3.1 reference: E[(U - Y)^2] = 1/3 for any world.

    Tolerance: within 10 000 ppm (one percentage point) of 333 333 ppm over
    ``N_MATCHES`` matches. If this drifts, the "beats a random agent" claim is
    being measured against something that is not a random agent.
    """
    assert scores(), "vacuous"
    assert abs(mean_of("random") - PPM_ONE // 3) < 10_000


def test_the_prior_only_scorer_is_between_random_and_bayes():
    """The three baselines must be ordered, otherwise the duels are meaningless."""
    assert scores(), "vacuous"
    assert mean_of("bayes") < mean_of("prior") < mean_of("random")
