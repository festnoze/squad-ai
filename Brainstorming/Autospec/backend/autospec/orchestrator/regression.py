"""Anti-regression detection (R2).

Compares the set of test node ids that were green before a story's build to the
real pytest outcomes after it, flagging any that were green and are now red — a
story that broke previously-passing tests.
"""

from __future__ import annotations


def find_regressions(prev_green: set[str], current: dict[str, str]) -> list[str]:
    """Node ids that were green before and now have a non-passing real outcome.

    Node ids absent from ``current`` are ignored (a test legitimately removed or
    renamed is not a regression), so only present-and-failing nodes are flagged.
    """
    return sorted(n for n in prev_green if n in current and current[n] != "passed")
