"""Persistence for Prediction Exchange: the projection database and the artefacts.

This package holds two independent halves and nothing else (CONTRACTS section
7.20):

* :mod:`pxe.store.models` and :mod:`pxe.store.db`, the SQLAlchemy Core
  **projection** database. Every table in it is derived from a journal or from a
  tournament level decision, so the whole database can be thrown away and
  rebuilt with ``Store.rebuild``. The journal on disk is the source of truth
  (section 4.1), never a row in here.
* :mod:`pxe.store.files`, the ``runs/<match_id>/`` artefact layout of section
  4.6 and the one builder of every path inside it.

This file is a docstring and nothing else: shared packages publish no name and
every consumer imports by full path (section 1), so
``from pxe.store.db import Store`` is the only spelling.
"""
