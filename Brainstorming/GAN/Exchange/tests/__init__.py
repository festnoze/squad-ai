"""Test package for Prediction Exchange.

This file exists so that ``tests`` is an importable package: ``mypy``'s
``[[tool.mypy.overrides]] module = "tests.*"`` block addresses it by dotted
name, and two workstreams writing ``helpers.py`` in a flat directory would
otherwise collide in ``sys.modules``.

Nothing is defined here on purpose. Shared fixtures live in
``tests/conftest.py`` (owner A01, see CONTRACTS section 10); a test module
never imports from another test module.
"""
