"""The oracle (A08): per market resolution, settlement, cancellation and unwind.

CONTRACTS section 7.11. Two modules, one responsibility each:

* :mod:`pxe.oracle.resolver` - :class:`~pxe.oracle.resolver.Oracle`, the single
  emitter of ``MarketResolved`` and ``MarketCancelled`` and the only thing in
  the engine that ever closes a market (CONTRACTS section 7.8);
* :mod:`pxe.oracle.settlement` - :func:`~pxe.oracle.settlement.settle`, the
  single emitter of ``SettlementApplied``.

Per CONTRACTS section 1 this file holds a docstring and nothing else: no
import and no re-export. Import submodules by full path, for example
``from pxe.oracle.resolver import Oracle``.
"""
