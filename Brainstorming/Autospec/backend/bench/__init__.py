"""Autospec measurement bench (docs/REFONTE_V2.md section 5).

The bench is independent of every factory it measures: it drives a factory
(v1, the bare harness, v2) through its own entry point, then judges the
produced workspace from the outside, in a clean environment rebuilt from the
product's manifest and lock, with hidden oracles that only use the public
interface fixed by each brief.
"""
