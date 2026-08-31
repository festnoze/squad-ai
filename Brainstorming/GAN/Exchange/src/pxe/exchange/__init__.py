"""The central limit order book of Prediction Exchange (CONTRACTS sections 7.7 to 7.9).

This package holds four modules and no re-export at all (CONTRACTS section 1:
a shared ``__init__.py`` carries a docstring and nothing else, because
``accounts.py`` and ``fees.py`` belong to a different workstream than
``book.py``, ``matching.py`` and ``exchange.py``). Import by full path:

* :mod:`pxe.exchange.book` - one price-time ordered book per market;
* :mod:`pxe.exchange.matching` - the pure matching planner, the FR-5.4.6
  reference price fallback chain and the FR-5.4.3 protection band;
* :mod:`pxe.exchange.exchange` - the facade that owns the order and trade
  counters and emits every order and trade event;
* :mod:`pxe.exchange.accounts` and :mod:`pxe.exchange.fees` - the ledger.
"""
