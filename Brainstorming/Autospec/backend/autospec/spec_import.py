"""Spec import (I3): normalize an imported specification document into a brief
that seeds a project, so the pipeline skips the PM interview and goes straight
to planning."""

from __future__ import annotations

MAX_BRIEF_CHARS = 20_000


def parse_spec_import(text: str) -> str:
    """Normalize imported spec text into a brief (trimmed and length-capped)."""
    return (text or "").strip()[:MAX_BRIEF_CHARS]


def parse_contract_import(brief: str, reference: str, *, reviewed_by: str, facts=()):
    """Independent acceptance import: preserve full sources, without the legacy
    interview brief's truncation. Extracted formal facts need explicit review."""
    from .contracts import import_contract

    return import_contract(brief, reference, reviewed_by=reviewed_by, facts=facts)
