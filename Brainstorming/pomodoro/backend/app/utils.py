"""Shared utility functions for the Pomodoro backend."""

import math


def calculate_level(xp: int) -> int:
    """Level = floor(sqrt(totalXP / 10))."""
    if xp <= 0:
        return 0
    return int(math.floor(math.sqrt(xp / 10)))
