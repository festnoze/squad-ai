"""Spec import (I3): normalize an imported specification document into a brief
that seeds a project, so the pipeline skips the PM interview and goes straight
to planning."""

from __future__ import annotations

MAX_BRIEF_CHARS = 20_000


def parse_spec_import(text: str) -> str:
    """Normalize imported spec text into a brief (trimmed and length-capped)."""
    return (text or "").strip()[:MAX_BRIEF_CHARS]
