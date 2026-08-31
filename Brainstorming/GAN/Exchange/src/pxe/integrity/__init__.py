"""Offline integrity detectors and the scripted cheater bench (CONTRACTS 7.18, A18).

This package holds two things and nothing else: :mod:`pxe.integrity.detectors`,
the offline projections that turn a finished journal into timestamped incidents
(PRD section 7.5), and :mod:`pxe.integrity.cheaters`, the scripted cheaters that
calibrate their thresholds (T5.5).

Detectors never influence a score. They read a
:class:`~pxe.metrics.projection.MatchProjection` and the incidents they raise are
deliberately outside the journal (CONTRACTS section 4.5), so bumping a detector
can never move a journal hash and can never change a ranking, a Brier or a
rating. That is PRD section 7.2's anti-hacking principle read literally: an
integrity alert is a description, never a penalty.

As every shared sub-package of ``pxe``, this file holds a docstring and no
import and no re-export (CONTRACTS section 1). Import by full path,
``from pxe.integrity.detectors import run_detectors``.
"""
