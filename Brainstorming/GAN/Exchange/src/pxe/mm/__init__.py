"""The reference market maker (A07, CONTRACTS section 7.10, PRD section 5.8).

The market maker is the liquidity thermostat of the arena: it is the only
guaranteed source of exogenous liquidity, so the spread it shows *is* the cost
of expressing a belief, and therefore the difficulty setting of the whole game.
It is uninformed (FR-5.8.2), neutral and out of the ranking (FR-5.8.5).

Per CONTRACTS section 1 this file holds a docstring and nothing else: no import
and no re-export. Import submodules by full path:

* :mod:`pxe.mm.market_maker` - :class:`~pxe.mm.market_maker.Quote` and
  :class:`~pxe.mm.market_maker.ReferenceMarketMaker`;
* :mod:`pxe.mm.profiles` - :func:`~pxe.mm.profiles.mm_config_for`, the three
  FR-5.8.6 presets, and the T2.6 cost of liquidity study.
"""
