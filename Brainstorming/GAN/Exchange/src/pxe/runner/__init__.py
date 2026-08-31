"""Match runner package: phases P1..P4, match state and replay (A09).

This package holds a docstring and nothing else, as CONTRACTS section 1
requires of every shared sub-package of ``pxe``: ``runner/`` is owned by A09
(``state.py``, ``match_runner.py``, ``replay.py``) plus A10
(``observation_builder.py``) and A11 (``action_validator.py``,
``schema_registry.py``), and a re-export here would both force one workstream
to edit another's publication point and create an import cycle between
``match_runner`` and ``observation_builder``.

Import submodules by their full path::

    from pxe.runner.state import MatchState
    from pxe.runner.match_runner import MatchRunner, run_match
    from pxe.runner.replay import replay_journal
"""
