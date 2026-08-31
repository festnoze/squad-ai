"""Tournament orchestration, scheduling, ratings, archives and reports.

This package holds **behaviour only**. The four pure data carriers that cross
the ``store`` boundary (``MatchTask``, ``TournamentConfig``,
``TournamentResult`` and ``RatingRecord``) live in :mod:`pxe.types`, because
:mod:`pxe.store` persists them and this package uses the store: defining them
here would make the two packages import each other (CONTRACTS section 7).

Per CONTRACTS section 1 this file carries a docstring and nothing else: no
import and no re-export. Three workstreams write in this directory (A19 the
orchestrator, the scheduling and the Latin square, A20 the ratings, the archives
and the held-out bank, A23 the report), so every consumer imports by full path,
for example ``from pxe.tournament.orchestrator import TournamentOrchestrator``.
"""
