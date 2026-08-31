"""``ToolResult`` (W4): the return type of every tool, in its own leaf module to break import cycles."""

from __future__ import annotations

from dataclasses import dataclass

from ala.shell import Effect


@dataclass(frozen=True, slots=True)
class ToolResult:
    ok: bool
    stdout: str
    effects: tuple[Effect, ...] = ()
    error: str | None = None
