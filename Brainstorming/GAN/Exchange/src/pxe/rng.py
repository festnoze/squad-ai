"""Deterministic RNG tree for Prediction Exchange (pxe).

Determinism is the top invariant of the product (O1, AC-P1). Every random draw
in the whole system comes from exactly one place: a :class:`RngTree` built from
a single integer root seed. Substreams are derived by stable hashing of their
name, never by Python's builtin ``hash()`` (which is salted per process).

Guarantees
----------
* Reproducible across processes, machines, OSes and CPython 3.11+ patch levels.
  Only three foundations are relied on: :func:`hashlib.blake2b` (stable by
  definition), the Mersenne Twister seeding of :class:`random.Random` from an
  integer, and :meth:`random.Random.getrandbits`. Those last two are the only
  parts of the standard library generator that CPython documents as frozen.
* **Every draw helper in this module is built on ``getrandbits`` alone.**
  ``shuffle``, ``random``, ``randrange``, ``gauss`` and ``betavariate`` of the
  standard library are never called: their algorithms are implementation
  details and they reach into the platform libm, which is not bit identical
  between glibc, msvcrt and macOS. The permutation, the uniform, the normal
  quantile, ``log`` and ``exp`` are implemented here and versioned by
  :data:`RNG_ALGORITHM_VERSION`.
* Two substreams never share state: each name maps to its own
  :class:`random.Random` instance.
* A substream instance is cached: asking twice for ``"info.news"`` returns the
  same object, so consumption keeps advancing exactly as the caller expects.

Rules for downstream modules
----------------------------
* Never call the module level :mod:`random` functions, ``numpy.random`` default
  state, ``secrets``, ``uuid4`` or the clock anywhere inside the engine.
* Any new source of randomness MUST take a named substream and that name MUST
  be registered in :data:`SUBSTREAMS` or :data:`SUBSTREAM_PREFIXES` in this
  file, in the same commit. Unregistered names raise
  :class:`~pxe.errors.UnknownSubstreamError`.
* Never iterate a ``set`` or a ``dict`` to feed randomness. Sort first, or use
  the helpers below which only accept sequences.
"""

import hashlib
import math
import random
from collections.abc import Iterable, Sequence
from typing import Any, TypeVar

from pxe.errors import UnknownSubstreamError

__all__ = [
    "SUBSTREAMS",
    "SUBSTREAM_PREFIXES",
    "RNG_ALGORITHM_VERSION",
    "RngTree",
    "derive_seed",
    "is_registered_substream",
    "shuffle_seeded",
    "choice",
    "choices_weighted",
    "sample_without_replacement",
    "random_unit",
    "random_open_unit",
    "normal",
    "lognormal",
    "bernoulli",
    "randint",
    "uniform",
    "beta",
    "stable_key",
    "ordered",
]

T = TypeVar("T")

_DIGEST_SIZE = 32
_SEPARATOR = b"\x1f"  # ASCII unit separator, cannot appear in a substream name


# --------------------------------------------------------------------------
# Substream registry
# --------------------------------------------------------------------------
#: Exact substream names. A name not listed here and not matching a registered
#: prefix is rejected. Names are lowercase dotted paths.
SUBSTREAMS: frozenset[str] = frozenset(
    {
        # world-gen
        "world.template",
        "world.latent",
        "world.markets",
        "world.correlation",
        "world.resolution",
        "world.outcome",
        "world.prior",
        # info-engine
        "info.schedule",
        "info.news",
        "info.noise",
        "info.signals",
        "info.profiles",
        # market maker
        "mm.tiebreak",
        # match runner: the only runner substream is the per tick family
        # "runner.tick_shuffle.<tick>" below. There is deliberately no second,
        # differently seeded agent ordering stream.
        # tournament orchestrator
        "tournament.pairing",
        "tournament.latin_square",
        "tournament.seeds",
        "tournament.heldout",
        # analytics
        "metrics.bootstrap",
        "integrity.bootstrap",
        "elites.mutation",
        # tests only
        "test.scratch",
    }
)

#: Registered parametric families. A name is accepted when it starts with one of
#: these prefixes followed by a dot and a non empty suffix, for example
#: ``"runner.tick_shuffle.17"`` or ``"agent.A3"``.
SUBSTREAM_PREFIXES: frozenset[str] = frozenset(
    {
        "runner.tick_shuffle",  # FR-5.1.5, one substream per tick
        "info.signals.tick",  # per tick signal draw
        "info.news.tick",  # per tick news draw
        "agent",  # per scripted agent, "agent.<agent_id>"
        "world.market",  # per market, "world.market.<market_id>"
        "test",  # test scaffolding only
    }
)


def is_registered_substream(name: str) -> bool:
    """Return True when ``name`` is an allowed substream name.

    Args:
        name: Dotted lowercase substream name.

    Returns:
        True when the name is registered exactly or through a prefix family.
    """
    if name in SUBSTREAMS:
        return True
    return any(name.startswith(prefix + ".") and len(name) > len(prefix) + 1 for prefix in SUBSTREAM_PREFIXES)


# --------------------------------------------------------------------------
# Seed derivation
# --------------------------------------------------------------------------
def derive_seed(root_seed: int, name: str) -> int:
    """Derive a stable 256 bit substream seed from a root seed and a name.

    The derivation is ``blake2b(uint64_be(root_seed) || 0x1f || utf8(name))``.
    It never uses Python's builtin ``hash()``.

    Args:
        root_seed: Non negative integer, the single seed of the match or run.
        name: Substream name. Not validated here, see :meth:`RngTree.substream`.

    Returns:
        A 256 bit non negative integer suitable for :class:`random.Random`.

    Raises:
        ValueError: If ``root_seed`` is negative or does not fit in 64 bits.
    """
    if root_seed < 0 or root_seed >= 2**64:
        raise ValueError(f"root_seed must fit in an unsigned 64 bit integer, got {root_seed}")
    digest = hashlib.blake2b(digest_size=_DIGEST_SIZE)
    digest.update(root_seed.to_bytes(8, "big", signed=False))
    digest.update(_SEPARATOR)
    digest.update(name.encode("utf-8"))
    return int.from_bytes(digest.digest(), "big")


class RngTree:
    """The single root of randomness of a match, a scenario or a tournament.

    A tree owns a root seed and a namespace. Substreams are addressed by name
    and cached, so repeated calls keep advancing the same generator.

    Example:
        >>> tree = RngTree(12345)
        >>> a = tree.substream("info.news")
        >>> b = tree.substream("info.news")
        >>> a is b
        True
        >>> RngTree(12345).substream("info.news").random() == RngTree(12345).substream("info.news").random()
        True
    """

    __slots__ = ("_root_seed", "_namespace", "_cache")

    def __init__(self, root_seed: int, namespace: str = "") -> None:
        """Build a tree.

        Args:
            root_seed: Unsigned 64 bit integer seed.
            namespace: Optional prefix prepended to every substream name before
                hashing. Used by :meth:`child` to build isolated sub-trees.

        Raises:
            ValueError: If ``root_seed`` is out of range.
        """
        if root_seed < 0 or root_seed >= 2**64:
            raise ValueError(f"root_seed must fit in an unsigned 64 bit integer, got {root_seed}")
        self._root_seed = int(root_seed)
        self._namespace = namespace
        self._cache: dict[str, random.Random] = {}

    @property
    def root_seed(self) -> int:
        """The unsigned 64 bit root seed."""
        return self._root_seed

    @property
    def namespace(self) -> str:
        """The namespace prefix applied to substream names before hashing."""
        return self._namespace

    def _qualified(self, name: str) -> str:
        return f"{self._namespace}/{name}" if self._namespace else name

    def substream(self, name: str) -> random.Random:
        """Return the cached generator for ``name``.

        Args:
            name: A registered substream name (see :data:`SUBSTREAMS`).

        Returns:
            A :class:`random.Random` dedicated to this name, cached for the
            lifetime of the tree.

        Raises:
            UnknownSubstreamError: If ``name`` is not registered.
        """
        if name not in self._cache:
            if not is_registered_substream(name):
                raise UnknownSubstreamError(
                    "substream name is not registered in pxe.rng.SUBSTREAMS",
                    name=name,
                )
            self._cache[name] = random.Random(derive_seed(self._root_seed, self._qualified(name)))
        return self._cache[name]

    def fresh_substream(self, name: str) -> random.Random:
        """Return a brand new, uncached generator for ``name``.

        Useful when a component wants a reproducible generator that always
        starts from the beginning, for example the per tick fairness shuffle.

        Args:
            name: A registered substream name.

        Returns:
            A new :class:`random.Random`, not stored in the cache.

        Raises:
            UnknownSubstreamError: If ``name`` is not registered.
        """
        if not is_registered_substream(name):
            raise UnknownSubstreamError(
                "substream name is not registered in pxe.rng.SUBSTREAMS",
                name=name,
            )
        return random.Random(derive_seed(self._root_seed, self._qualified(name)))

    def child(self, namespace: str) -> "RngTree":
        """Return an isolated sub-tree under an additional namespace.

        Args:
            namespace: Namespace segment, appended to the current one.

        Returns:
            A new :class:`RngTree` sharing the root seed but hashing names under
            the extended namespace, so its substreams never collide with the
            parent's.
        """
        ns = f"{self._namespace}/{namespace}" if self._namespace else namespace
        return RngTree(self._root_seed, ns)

    def seed_for(self, name: str) -> int:
        """Return the derived integer seed for ``name`` without building a generator.

        Args:
            name: A registered substream name.

        Returns:
            The 256 bit derived seed.

        Raises:
            UnknownSubstreamError: If ``name`` is not registered.
        """
        if not is_registered_substream(name):
            raise UnknownSubstreamError(
                "substream name is not registered in pxe.rng.SUBSTREAMS",
                name=name,
            )
        return derive_seed(self._root_seed, self._qualified(name))

    def __repr__(self) -> str:
        """Render the root seed and the namespace, never a memory address."""
        return f"RngTree(root_seed={self._root_seed}, namespace={self._namespace!r})"


# --------------------------------------------------------------------------
# Pinned floating point primitives
#
# CPython's ``random.Random`` exposes exactly two primitives whose behaviour is
# documented and frozen: ``getrandbits`` and the Mersenne Twister seeding from
# an integer. Everything else (``shuffle``, ``gauss``, ``betavariate``,
# ``random``) is an implementation detail that has changed between releases and
# that calls into the platform's libm for ``log``, ``exp``, ``cos`` and
# ``sqrt``. libm transcendentals are not bit identical between glibc, msvcrt
# and macOS, so a value landing within one ulp of a ``_milli`` boundary would
# quantise differently on two machines and the whole world would diverge.
#
# Therefore every draw below is built from ``getrandbits`` and from operations
# that IEEE-754 requires to be correctly rounded (``+``, ``-``, ``*``, ``/``,
# ``math.sqrt``) or exact (``math.frexp``, ``math.ldexp``, ``math.floor``).
# ``log`` and ``exp`` are implemented here in fixed order arithmetic, so the
# algorithm is versioned by :data:`RNG_ALGORITHM_VERSION` and by nothing else.
#
# Changing anything in this section moves every golden journal hash. Bump
# :data:`RNG_ALGORITHM_VERSION` and ``pxe.types.ENGINE_VERSION`` in the same
# commit and regenerate ``tests/golden/``.
# --------------------------------------------------------------------------
#: Version of the draw algorithms in this module. It is part of the determinism
#: contract: two runs agree only when this string agrees.
RNG_ALGORITHM_VERSION: str = "1.0.0"

_TWO_POW_53 = 9007199254740992.0  # 2**53, exact in IEEE-754 double
_SQRT_HALF = float.fromhex("0x1.6a09e667f3bcdp-1")  # nearest double to 1/sqrt(2)
_LN2_HI = float.fromhex("0x1.62e42feep-1")  # leading bits of ln 2
_LN2_LO = float.fromhex("0x1.a39ef35793c76p-33")  # trailing bits of ln 2
_INV_LN2 = float.fromhex("0x1.71547652b82fep+0")  # nearest double to 1 / ln 2

#: Coefficients ``1 / (2k + 1)`` of the atanh series used by :func:`_log`.
#: Built by correctly rounded divisions, so the values are identical on every
#: conforming platform.
_ATANH_COEFFS: tuple[float, ...] = tuple(1.0 / float(2 * k + 1) for k in range(13))

#: Coefficients ``1 / k!`` of the Taylor series used by :func:`_exp`.
_EXP_COEFFS: tuple[float, ...] = tuple(1.0 / float(math.factorial(k)) for k in range(17))

# Acklam's rational approximation of the inverse normal CDF. Relative error is
# below 1.15e-9 over the whole range, far finer than the ``_milli``
# quantisation every consumer applies. Only + - * / and sqrt are involved.
_PPF_A = (
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285104469687e02,
    1.383577518672690e02,
    -3.066479806614716e01,
    2.506628277459239e00,
)
_PPF_B = (
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
)
_PPF_C = (
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
)
_PPF_D = (
    7.784695709041462e-03,
    3.224671290700398e-01,
    2.445134137142996e00,
    3.754408661907416e00,
)
_PPF_LOW = 0.02425
_PPF_HIGH = 1.0 - _PPF_LOW


def _log(x: float) -> float:
    """Natural logarithm, computed in fixed order IEEE-754 arithmetic.

    ``math.log`` delegates to the platform libm, which is not required to be
    correctly rounded and differs between operating systems. This routine uses
    only exact operations (``math.frexp``, multiplication by 2) and correctly
    rounded ones, so its result is bit identical everywhere.

    Args:
        x: Strictly positive finite float.

    Returns:
        ``ln(x)``, accurate to about one ulp.

    Raises:
        ValueError: If ``x`` is not strictly positive or is not finite.
    """
    if not x > 0.0 or math.isinf(x) or math.isnan(x):
        raise ValueError(f"log domain error: {x!r}")
    mantissa, exponent = math.frexp(x)  # x == mantissa * 2**exponent, exact
    if mantissa < _SQRT_HALF:
        mantissa *= 2.0  # exact
        exponent -= 1
    s = (mantissa - 1.0) / (mantissa + 1.0)
    s2 = s * s
    acc = _ATANH_COEFFS[-1]
    for index in range(len(_ATANH_COEFFS) - 2, -1, -1):
        acc = acc * s2 + _ATANH_COEFFS[index]
    scale = float(exponent)
    return (2.0 * s) * acc + (scale * _LN2_LO + scale * _LN2_HI)


def _exp(x: float) -> float:
    """Exponential, computed in fixed order IEEE-754 arithmetic.

    Args:
        x: Finite float.

    Returns:
        ``e ** x``, accurate to about one ulp.

    Raises:
        ValueError: If ``x`` is not finite.
        OverflowError: If the result is not representable.
    """
    if math.isnan(x) or math.isinf(x):
        raise ValueError(f"exp domain error: {x!r}")
    n = math.floor(x * _INV_LN2 + 0.5)
    scale = float(n)
    r = (x - scale * _LN2_HI) - scale * _LN2_LO
    acc = _EXP_COEFFS[-1]
    for index in range(len(_EXP_COEFFS) - 2, -1, -1):
        acc = acc * r + _EXP_COEFFS[index]
    return math.ldexp(acc, n)


def _norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam), in correctly rounded arithmetic only.

    Args:
        p: Probability strictly inside ``(0, 1)``.

    Returns:
        The standard normal quantile.

    Raises:
        ValueError: If ``p`` is outside ``(0, 1)``.
    """
    if not 0.0 < p < 1.0:
        raise ValueError(f"normal quantile needs p in (0, 1), got {p!r}")
    if p < _PPF_LOW or p > _PPF_HIGH:
        tail = p if p < _PPF_LOW else 1.0 - p
        q = math.sqrt(-2.0 * _log(tail))
        num = ((((_PPF_C[0] * q + _PPF_C[1]) * q + _PPF_C[2]) * q + _PPF_C[3]) * q + _PPF_C[4]) * q + _PPF_C[5]
        den = (((_PPF_D[0] * q + _PPF_D[1]) * q + _PPF_D[2]) * q + _PPF_D[3]) * q + 1.0
        value = num / den
        return value if p < _PPF_LOW else -value
    q = p - 0.5
    r = q * q
    num = (((((_PPF_A[0] * r + _PPF_A[1]) * r + _PPF_A[2]) * r + _PPF_A[3]) * r + _PPF_A[4]) * r + _PPF_A[5]) * q
    den = ((((_PPF_B[0] * r + _PPF_B[1]) * r + _PPF_B[2]) * r + _PPF_B[3]) * r + _PPF_B[4]) * r + 1.0
    return num / den


def _randbelow(rng: random.Random, n: int) -> int:
    """Uniform integer in ``[0, n)`` drawn from ``getrandbits`` alone.

    Rejection sampling on the smallest number of bits that covers ``n``. This is
    the only integer primitive in pxe; ``randrange``, ``randint``, ``choice``
    and ``shuffle`` of the standard library are never called because their
    algorithms are implementation details.

    Args:
        rng: Generator obtained from :meth:`RngTree.substream`.
        n: Strictly positive bound, exclusive.

    Returns:
        An integer in ``[0, n)``.

    Raises:
        ValueError: If ``n`` is not strictly positive.
    """
    if n <= 0:
        raise ValueError(f"bound must be strictly positive, got {n}")
    if n == 1:
        return 0
    bits = (n - 1).bit_length()
    while True:
        candidate = rng.getrandbits(bits)
        if candidate < n:
            return candidate


def random_unit(rng: random.Random) -> float:
    """Draw a float in ``[0, 1)`` on the ``2**-53`` grid.

    Equivalent in distribution to ``random.Random.random`` but pinned here: the
    numerator comes from ``getrandbits(53)`` and the division by ``2**53`` is
    exact, so the result cannot move with a CPython release.

    Args:
        rng: Generator.

    Returns:
        A float in ``[0, 1)``.
    """
    return rng.getrandbits(53) / _TWO_POW_53


def random_open_unit(rng: random.Random) -> float:
    """Draw a float strictly inside ``(0, 1)`` on the ``2**-53`` grid.

    Used wherever a zero would be a domain error (``log``, quantiles). The
    numerator is an odd integer below ``2**53``, so the division by ``2**53``
    is exact.

    Args:
        rng: Generator.

    Returns:
        A float in ``(0, 1)``.
    """
    return (rng.getrandbits(52) * 2 + 1) / _TWO_POW_53


# --------------------------------------------------------------------------
# Public draw helpers. All of them take an explicit generator and only accept
# sequences, never sets or dict views, so iteration order can never leak in.
# --------------------------------------------------------------------------
def shuffle_seeded(rng: random.Random, items: Sequence[T]) -> list[T]:
    """Return a shuffled copy of ``items`` (the input is never mutated).

    Fisher-Yates driven by :func:`_randbelow`. ``random.Random.shuffle`` is
    deliberately not used: its algorithm is an implementation detail, and a
    CPython change to it would move every golden journal hash while looking
    like a determinism bug in pxe.

    Args:
        rng: Generator obtained from :meth:`RngTree.substream`.
        items: Any sequence. Callers must pass a deterministically ordered one.

    Returns:
        A new list holding the same elements in shuffled order.
    """
    out = list(items)
    for i in range(len(out) - 1, 0, -1):
        j = _randbelow(rng, i + 1)
        out[i], out[j] = out[j], out[i]
    return out


def choice(rng: random.Random, items: Sequence[T]) -> T:
    """Return one uniformly drawn element of ``items``.

    Args:
        rng: Generator.
        items: Non empty sequence.

    Returns:
        The drawn element.

    Raises:
        IndexError: If ``items`` is empty.
    """
    if not items:
        raise IndexError("cannot draw from an empty sequence")
    return items[_randbelow(rng, len(items))]


def choices_weighted(rng: random.Random, items: Sequence[T], weights: Sequence[float], k: int = 1) -> list[T]:
    """Draw ``k`` elements with replacement using positive weights.

    The cumulative sum is walked in the order the caller supplied, so the result
    depends only on that order and on :func:`random_unit`.

    Args:
        rng: Generator.
        items: Non empty sequence.
        weights: Same length as ``items``, non negative, sum strictly positive.
        k: Number of draws.

    Returns:
        A list of ``k`` drawn elements.

    Raises:
        ValueError: On length mismatch, negative weights or a null total.
    """
    if len(items) != len(weights):
        raise ValueError("items and weights must have the same length")
    if any(w < 0.0 for w in weights):
        raise ValueError("weights must be non negative with a strictly positive sum")
    total = 0.0
    for weight in weights:
        total += float(weight)
    if total <= 0.0:
        raise ValueError("weights must be non negative with a strictly positive sum")
    out: list[T] = []
    for _ in range(k):
        target = random_unit(rng) * total
        acc = 0.0
        picked = items[-1]
        for item, weight in zip(items, weights, strict=True):
            acc += weight
            if target < acc:
                picked = item
                break
        out.append(picked)
    return out


def sample_without_replacement(rng: random.Random, items: Sequence[T], k: int) -> list[T]:
    """Draw ``k`` distinct elements, preserving a deterministic draw order.

    Args:
        rng: Generator.
        items: Sequence to draw from.
        k: Number of elements, clamped to ``len(items)``.

    Returns:
        A list of ``min(k, len(items))`` elements.
    """
    k = max(0, min(k, len(items)))
    return shuffle_seeded(rng, items)[:k]


def normal(rng: random.Random, mu: float = 0.0, sigma: float = 1.0) -> float:
    """Draw from a normal distribution, reproducibly on every platform.

    One uniform draw is mapped through the pinned inverse normal CDF. Box-Muller
    and ``random.Random.gauss`` are not used: they call libm ``cos``/``log``,
    and ``gauss`` caches a spare value, which makes consumption depend on the
    call history.

    Args:
        rng: Generator.
        mu: Mean.
        sigma: Standard deviation, must be non negative.

    Returns:
        The drawn value.

    Raises:
        ValueError: If ``sigma`` is negative.
    """
    if sigma < 0.0:
        raise ValueError("sigma must be non negative")
    return mu + sigma * _norm_ppf(random_open_unit(rng))


def lognormal(rng: random.Random, mu: float = 0.0, sigma: float = 1.0) -> float:
    """Draw from a log normal distribution.

    Args:
        rng: Generator.
        mu: Mean of the underlying normal.
        sigma: Standard deviation of the underlying normal.

    Returns:
        The drawn value, strictly positive.
    """
    return _exp(normal(rng, mu, sigma))


def bernoulli(rng: random.Random, p: float) -> bool:
    """Draw a Bernoulli variable.

    Args:
        rng: Generator.
        p: Success probability in ``[0, 1]``.

    Returns:
        True with probability ``p``.

    Raises:
        ValueError: If ``p`` is outside ``[0, 1]``.
    """
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"p must be in [0, 1], got {p}")
    return random_unit(rng) < p


def randint(rng: random.Random, low: int, high: int) -> int:
    """Draw a uniform integer in the inclusive range ``[low, high]``.

    Args:
        rng: Generator.
        low: Lower bound, inclusive.
        high: Upper bound, inclusive.

    Returns:
        The drawn integer.

    Raises:
        ValueError: If ``high < low``.
    """
    if high < low:
        raise ValueError(f"empty range [{low}, {high}]")
    return low + _randbelow(rng, high - low + 1)


def uniform(rng: random.Random, low: float = 0.0, high: float = 1.0) -> float:
    """Draw a uniform float in ``[low, high)``.

    Args:
        rng: Generator.
        low: Lower bound.
        high: Upper bound.

    Returns:
        The drawn value.
    """
    return low + (high - low) * random_unit(rng)


def _gamma_variate(rng: random.Random, alpha: float) -> float:
    """Draw from ``Gamma(alpha, 1)`` with the Marsaglia-Tsang method.

    Built on :func:`_norm_ppf`, :func:`_log` and :func:`_exp`, so it inherits
    their cross platform reproducibility. ``random.Random.gammavariate`` is not
    used.

    Args:
        rng: Generator.
        alpha: Shape parameter, strictly positive.

    Returns:
        The drawn value, strictly positive.
    """
    if alpha < 1.0:
        boosted = _gamma_variate(rng, alpha + 1.0)
        u = random_open_unit(rng)
        return boosted * _exp(_log(u) / alpha)
    d = alpha - 1.0 / 3.0
    c = 1.0 / math.sqrt(9.0 * d)
    while True:
        x = _norm_ppf(random_open_unit(rng))
        v = 1.0 + c * x
        if v <= 0.0:
            continue
        v = v * v * v
        u = random_open_unit(rng)
        if _log(u) < 0.5 * x * x + d - d * v + d * _log(v):
            return d * v


def beta(rng: random.Random, alpha: float, beta_param: float) -> float:
    """Draw from a Beta distribution.

    Implemented as ``X / (X + Y)`` with ``X ~ Gamma(alpha)`` and
    ``Y ~ Gamma(beta_param)``, both from :func:`_gamma_variate`.

    Args:
        rng: Generator.
        alpha: First shape parameter, strictly positive.
        beta_param: Second shape parameter, strictly positive.

    Returns:
        A value in ``[0, 1]``.

    Raises:
        ValueError: If a shape parameter is not strictly positive.
    """
    if alpha <= 0.0 or beta_param <= 0.0:
        raise ValueError("beta shape parameters must be strictly positive")
    x = _gamma_variate(rng, alpha)
    y = _gamma_variate(rng, beta_param)
    total = x + y
    if total <= 0.0:
        return 0.5
    return x / total


def stable_key(*parts: Any) -> str:
    """Build a substream suffix from arbitrary parts, in a stable way.

    Args:
        *parts: Values converted with ``str`` and joined by ``"."``.

    Returns:
        The joined suffix, for example ``stable_key("A1", 17) == "A1.17"``.
    """
    return ".".join(str(p) for p in parts)


def ordered(items: Iterable[T]) -> list[T]:
    """Return a sorted list, to defend against set or dict ordering leaks.

    Args:
        items: Any iterable of comparable items.

    Returns:
        A new sorted list.
    """
    return sorted(items)  # type: ignore[type-var]
