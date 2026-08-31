"""The ``python`` tool (W4): a tiny deterministic calculator sandbox.

The agent passes ``code`` that computes and assigns ``result``. The namespace has no imports, no file
access, no builtins beyond a math allowlist, and no time or randomness (any randomness must come from
the passed rng, which the scripted agents do not use here). This keeps the tool deterministic and safe:
it is a calculator, not an escape hatch. The real machine is reached through ``sh``, not through here.
"""

from __future__ import annotations

import random
from collections.abc import Mapping

from ala.kernel import Kernel
from ala.tools.result import ToolResult
from ala.types import AgentId

# A small allowlist. No __import__, no open, no eval, no getattr.
_SAFE_BUILTINS: dict[str, object] = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "sum": sum,
    "len": len,
    "int": int,
    "pow": pow,
    "range": range,
    "sorted": sorted,
}

_MAX_CODE_LEN = 2000


def apply_python(kernel: Kernel, actor: AgentId, args: Mapping[str, str], rng: random.Random) -> ToolResult:
    code = args.get("code", "")
    if len(code) > _MAX_CODE_LEN:
        return ToolResult(False, "", error="code too long")
    if "__" in code or "import" in code:
        return ToolResult(False, "", error="forbidden token")
    namespace: dict[str, object] = {"__builtins__": _SAFE_BUILTINS}
    try:
        exec(code, namespace)
    except Exception as exc:
        return ToolResult(False, "", error=f"exec error: {type(exc).__name__}")
    result = namespace.get("result")
    if result is None:
        return ToolResult(True, "", ())
    return ToolResult(True, str(result), ())
