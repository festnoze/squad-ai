"""Scripted agents of Prediction Exchange (pxe).

This package holds the :class:`~pxe.agents.base.ScriptedAgent` protocol that
every non LLM player implements, and the six reference baselines that give the
arena a population without spending a token (CONTRACTS section 7.15).

Per CONTRACTS section 1 this ``__init__`` carries a docstring and nothing else:
no import and no re-export. Import by full path
(``from pxe.agents.base import make_baseline``), never from the package.
"""
