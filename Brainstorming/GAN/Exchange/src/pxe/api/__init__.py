"""The read only replay API (CONTRACTS section 7.21, A22).

``pxe.api`` serves finished matches and finished tournaments over HTTP and over
one WebSocket. It computes no engine logic: every number it returns already
exists in an artefact, either in ``runs/<match_id>/journal.jsonl``, in the
``MatchProjection`` :mod:`pxe.metrics` folds out of it, in
``runs/<match_id>/metrics.json`` or in the :class:`~pxe.store.db.Store`
projection database.

The package is strictly read only. There is no POST, PUT, PATCH or DELETE
route anywhere in it, and a request using one of those verbs is refused with
``405`` whatever the path (CONTRACTS decision 33).

This file holds a docstring and nothing else, as every sub-package
``__init__.py`` of ``pxe`` does (CONTRACTS section 1). Import by full path:

* :func:`pxe.api.app.create_app` and :data:`pxe.api.app.API_VERSION`;
* :class:`pxe.api.routes.ReplayService` and the payload models;
* :func:`pxe.api.ws.build_ws_router` for the streaming half.
"""
