"""Information engine (A04): public news, private signals, profiles and noise.

The engine is the only thing standing between the world's hidden latent process
(A03) and what an agent is allowed to know. Two channels leave it, and they are
deliberately different in kind:

* **Public news** (:meth:`pxe.info.engine.InfoEngine.news_for_tick`) is the same
  for every agent at the same tick. Each item carries a
  :class:`pxe.types.NewsImpact` tag, which is the *fact* that information landed
  and never its direction; the reference market maker widens on ``HIGH`` and on
  nothing else (FR-5.8.4).
* **Private signals** (:meth:`pxe.info.engine.InfoEngine.signals_for_tick`) are
  0 to 2 per agent per tick, shaped by that seat's
  :class:`pxe.types.InfoProfile` (generalist, event specialist, delayed), which
  the Latin square of FR-5.3.2 permutes across seats.

Both are noisy observations of the same latent state, so an agent that reads its
signals well is measurably better off than one that ignores them (FR-5.3.1).

Per CONTRACTS section 1 this file holds a docstring and nothing else: no import
and no re-export. Import submodules by full path, for example
``from pxe.info.engine import InfoEngine``.
"""
