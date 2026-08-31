"""Metric projections over a finished journal (CONTRACTS sections 7.17 and 9).

Every metric of this package is computed from a
:class:`~pxe.metrics.projection.MatchProjection`, itself built from the journal
alone by :func:`~pxe.metrics.projection.project`. Nothing here reads engine
state, and nothing here writes an event.

This ``__init__`` holds a docstring and nothing else (CONTRACTS section 1):
submodules are always imported by full path, for example
``from pxe.metrics.projection import project``.
"""
