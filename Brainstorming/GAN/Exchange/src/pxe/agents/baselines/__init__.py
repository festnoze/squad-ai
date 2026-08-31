"""The six scripted baselines, one per module (CONTRACTS section 7.15).

A baseline module is reached only through
:func:`pxe.agents.base.make_baseline`; nothing outside ``pxe.agents`` imports
one by name. Per CONTRACTS section 1 this ``__init__`` carries a docstring and
nothing else: no import and no re-export.
"""
