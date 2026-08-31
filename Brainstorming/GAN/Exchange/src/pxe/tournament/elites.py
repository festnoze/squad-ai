"""The MAP-Elites archive over the behavioral descriptors (PRD 8, CONTRACTS 7.19, A20).

PRD section 8 asks for "une grille 2-3 D sur les descripteurs 7.4; l'elite d'une
cellule est la version au meilleur mu TrueSkill presentant ce style". This module
is that sentence, and nothing more:

* the grid has 2 or 3 axes, chosen among the six names
  :data:`pxe.metrics.behavioral.DESCRIPTOR_NAMES` publishes, with a configurable
  number of bins per axis;
* a candidate is a triple ``(harness_key, mu, descriptors)`` and it is offered,
  never inserted: the occupant of a cell is the best ``mu`` seen for that style;
* the descriptors come from a
  :class:`~pxe.metrics.behavioral.BehavioralDescriptors` block, which A17
  computes from a :class:`~pxe.metrics.projection.MatchProjection`, which is
  folded from the journal alone. An archive is therefore rebuildable a year later
  from ``runs/*/journal.jsonl`` and lands in the same cells.

Why the axis bounds are declared here
-------------------------------------
Binning needs an upper bound per axis and the six descriptors do not share one.
The four ``_ppm`` axes are ratios and their bound is :data:`pxe.types.PPM_ONE`.
The two ``_milli`` axes are durations in thousandths of a tick, and section 9
only says they are "capped at the horizon", which is the match length and is not
known to an archive: :class:`EliteArchive` receives axes and bins, not a
:class:`~pxe.types.MatchConfig`. The bound used is therefore the longest legal
match, ``MatchConfig.__post_init__`` capping ``ticks_total`` at 96, so a duration
descriptor can never fall outside the grid whatever the scenario. A value above
its bound lands in the top bin rather than raising, which is the same clamping
the descriptor itself already applies. This is reported as a contract gap: the
alternative (an axis scale on the constructor) would have widened a literal
section 7.19 signature.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from pxe.errors import InvalidConfigError
from pxe.metrics.behavioral import DESCRIPTOR_NAMES, BehavioralDescriptors
from pxe.types import MILLI_ONE, PPM_ONE

__all__ = [
    "AXIS_MAX",
    "MAX_AXES",
    "MIN_AXES",
    "DEFAULT_ELITE_AXES",
    "DEFAULT_ELITE_BINS",
    "EliteCell",
    "EliteArchive",
]

#: Longest legal match, from ``MatchConfig.__post_init__`` (``24 <= ticks_total
#: <= 96``). It is the bound of every duration axis, so a ``_milli`` descriptor
#: is always inside the grid.
_MAX_TICKS_TOTAL = 96

#: Inclusive upper bound of every axis, derived from the descriptor name so a
#: seventh descriptor added by A17 needs no edit here: a ratio ends in ``_ppm``
#: and is bounded by ``PPM_ONE``, a duration ends in ``_milli`` and is bounded by
#: the longest legal match.
AXIS_MAX: Mapping[str, int] = MappingProxyType(
    {name: (MILLI_ONE * _MAX_TICKS_TOTAL if name.endswith("_milli") else PPM_ONE) for name in DESCRIPTOR_NAMES}
)

#: PRD section 8: "grille 2-3 D". Fewer than two axes is a leaderboard, not an
#: archive, and more than three is a grid nobody can read on a tournament view.
MIN_AXES = 2
MAX_AXES = 3

#: The grid a tournament builds when nobody chooses one, and therefore the grid
#: every stored ``elite_cell`` row belongs to. It is the **leading three** names
#: of :data:`~pxe.metrics.behavioral.DESCRIPTOR_NAMES`, in that order, so a
#: consumer holding only the coordinate arity can label the axes exactly
#: (``pxe.api.routes`` does, section 7.21's ``Elites``). Ten bins per axis is
#: the finest grid that keeps a three axis archive at a thousand cells, which is
#: a grid a tournament view can draw.
DEFAULT_ELITE_AXES: tuple[str, ...] = DESCRIPTOR_NAMES[:MAX_AXES]

#: Bin count per axis of :data:`DEFAULT_ELITE_AXES`.
DEFAULT_ELITE_BINS: tuple[int, ...] = (10,) * MAX_AXES


@dataclass(frozen=True, slots=True)
class EliteCell:
    """One occupied cell of the archive.

    Attributes:
        coords: Bin index per axis, aligned with the ``axes`` of the archive.
        harness_key: The elite, that is the best ``mu`` seen with this style.
        mu: Its TrueSkill mean at the time it was offered.
        descriptors: The raw descriptor values of the occupant, aligned with
            ``coords``, so a report can show where inside its cell an elite sits.
    """

    coords: tuple[int, ...]
    harness_key: str
    mu: float
    descriptors: tuple[int, ...]


class EliteArchive:
    """A MAP-Elites grid over 2 or 3 behavioral axes (T5.2).

    The archive is a pure in memory projection: it holds no journal, no store and
    no clock. Persistence is :meth:`pxe.store.db.Store.save_elites`, which is
    also the one place :class:`EliteCell` crosses into ``pxe.store``
    (section 7.20).
    """

    __slots__ = ("_axes", "_bins", "_cells")

    def __init__(self, *, axes: Sequence[str], bins: Sequence[int]) -> None:
        """Build an empty archive.

        Args:
            axes: Two or three descriptor names, taken from
                :data:`pxe.metrics.behavioral.DESCRIPTOR_NAMES`. The order is the
                order of ``coords``.
            bins: Number of bins per axis, aligned with ``axes``, each at least
                one.

        Raises:
            InvalidConfigError: If the number of axes is outside 2..3, if
                ``bins`` is not aligned with ``axes``, if an axis is unknown or
                repeated, or if a bin count is below one.
        """
        if not MIN_AXES <= len(axes) <= MAX_AXES:
            raise InvalidConfigError("a MAP-Elites grid has 2 or 3 axes (PRD section 8)", n_axes=len(axes))
        if len(bins) != len(axes):
            raise InvalidConfigError("bins must be aligned with axes", n_axes=len(axes), n_bins=len(bins))
        for name in axes:
            if name not in AXIS_MAX:
                raise InvalidConfigError(
                    "unknown behavioral axis; see pxe.metrics.behavioral.DESCRIPTOR_NAMES",
                    axis=name,
                )
        if len(set(axes)) != len(axes):
            raise InvalidConfigError("an axis may not appear twice", axes=tuple(axes))
        for name, count in zip(axes, bins, strict=True):
            if count < 1:
                raise InvalidConfigError("an axis needs at least one bin", axis=name, bins=count)
        self._axes: tuple[str, ...] = tuple(axes)
        self._bins: tuple[int, ...] = tuple(int(count) for count in bins)
        self._cells: dict[tuple[int, ...], EliteCell] = {}

    @property
    def axes(self) -> tuple[str, ...]:
        """Return the descriptor names of the grid, in coordinate order.

        Published because ``coords`` alone is an unlabelled tuple: a report and
        a tournament view both have to name the axis they are drawing, and
        without this the only way to do it is to duplicate the caller's
        construction arguments (section 7.19).
        """
        return self._axes

    @property
    def bins(self) -> tuple[int, ...]:
        """Return the bin count per axis, aligned with :attr:`axes`."""
        return self._bins

    def coords_for(self, descriptors: BehavioralDescriptors) -> tuple[int, ...]:
        """Return the cell coordinates of one style vector.

        Args:
            descriptors: The behavioral block A17 computed for one seat.

        Returns:
            One bin index per axis, in the order the axes were declared.
        """
        return tuple(
            _bin_index(_axis_value(descriptors, name), AXIS_MAX[name], count)
            for name, count in zip(self._axes, self._bins, strict=True)
        )

    def offer(self, *, harness_key: str, mu: float, descriptors: BehavioralDescriptors) -> bool:
        """Offer a harness for the cell its style falls into.

        The occupant of a cell is the best ``mu``. An offer with an equal ``mu``
        does **not** displace the incumbent, so the archive never depends on the
        order two equally rated harnesses were offered in.

        Args:
            harness_key: The candidate, from :func:`pxe.types.harness_key`.
            mu: Its TrueSkill mean.
            descriptors: Its style vector.

        Returns:
            ``True`` when the candidate took the cell, ``False`` when it did not.

        Raises:
            InvalidConfigError: If ``harness_key`` is empty.
        """
        if not harness_key:
            raise InvalidConfigError("a candidate needs a harness key")
        coords = self.coords_for(descriptors)
        incumbent = self._cells.get(coords)
        if incumbent is not None and float(mu) <= incumbent.mu:
            return False
        self._cells[coords] = EliteCell(
            coords=coords,
            harness_key=harness_key,
            mu=float(mu),
            descriptors=tuple(_axis_value(descriptors, name) for name in self._axes),
        )
        return True

    def cells(self) -> tuple[EliteCell, ...]:
        """Return every occupied cell, ordered by coordinates.

        The order is ascending on the coordinate tuple, which is a total order on
        a fixed number of axes, so two archives filled in two different orders
        publish the same grid.

        Returns:
            The occupied cells. Empty until the first accepted offer.
        """
        return tuple(self._cells[coords] for coords in sorted(self._cells))


def _axis_value(descriptors: BehavioralDescriptors, axis: str) -> int:
    """Return one descriptor of a style vector by axis name.

    Args:
        descriptors: The behavioral block.
        axis: One of :data:`pxe.metrics.behavioral.DESCRIPTOR_NAMES`.

    Returns:
        The integer descriptor value.
    """
    return int(getattr(descriptors, axis))


def _bin_index(value: int, axis_max: int, n_bins: int) -> int:
    """Return the bin of ``value`` on an axis bounded by ``axis_max``.

    Integer arithmetic only, so a bin edge cannot move with a floating point
    rounding mode. Values at or above the bound land in the top bin and negative
    values (which no descriptor produces) land in the bottom one.

    Args:
        value: The descriptor value.
        axis_max: Inclusive upper bound of the axis.
        n_bins: Number of bins, at least one.

    Returns:
        An index in ``0..n_bins - 1``.
    """
    if value <= 0:
        return 0
    return min(n_bins - 1, (value * n_bins) // axis_max)
