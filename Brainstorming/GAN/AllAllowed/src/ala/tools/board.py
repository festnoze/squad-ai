"""The messaging tools (W4): board_post, board_read, dm.

The board is a directory on the vfs, one subdirectory per channel. ``board_post`` is really an
``echo text > /board/<channel>/<key>``: there is no privileged messaging bus, so if this tool were
removed an agent with a shell would reinvent it, which is exactly the "phase one" finding to reproduce.
A dm is a file dropped into the recipient's inbox, which is a drop-box directory the recipient owns.
"""

from __future__ import annotations

import random
import re
from collections.abc import Mapping

from ala.errors import PathNotFound, PermissionDenied
from ala.kernel import Kernel
from ala.shell import Effect
from ala.tools.result import ToolResult
from ala.types import AgentId, Role

_SAFE = re.compile(r"[^A-Za-z0-9_.:\-]")


def _slug(text: str) -> str:
    return _SAFE.sub("_", text)[:64] or "empty"


def apply_board_post(
    kernel: Kernel, actor: AgentId, args: Mapping[str, str], rng: random.Random
) -> ToolResult:
    channel = _slug(args["channel"])
    key = _slug(args["key"])
    text = args.get("text", "")
    path = f"/board/{channel}/{key}"
    role = kernel.accounts.role(actor) if kernel.accounts.exists(actor) else Role.USER
    if not kernel.vfs.exists(f"/board/{channel}"):
        from ala.types import MODE_777

        try:
            kernel.vfs.mkdir(f"/board/{channel}", "root", MODE_777)
        except (PathNotFound, PermissionDenied) as exc:
            return ToolResult(False, "", error=f"no board: {exc}")
    try:
        kernel.vfs.write(path, text.encode("utf-8"), actor=actor, actor_role=role)
    except (PermissionDenied, PathNotFound) as exc:
        return ToolResult(False, "", error=str(exc))
    return ToolResult(
        True,
        "",
        (Effect("board_post", {"channel": channel, "key": key, "path": path}),),
    )


def apply_board_read(
    kernel: Kernel, actor: AgentId, args: Mapping[str, str], rng: random.Random
) -> ToolResult:
    channel = _slug(args["channel"])
    prefix = args.get("prefix", "")
    role = kernel.accounts.role(actor) if kernel.accounts.exists(actor) else Role.USER
    base = f"/board/{channel}"
    if not kernel.vfs.exists(base):
        return ToolResult(True, "", ())
    try:
        keys = kernel.vfs.listdir(base, actor=actor, actor_role=role)
    except (PermissionDenied, PathNotFound) as exc:
        return ToolResult(False, "", error=str(exc))
    lines = []
    for key in keys:
        if prefix and not key.startswith(prefix):
            continue
        try:
            content = kernel.vfs.read(f"{base}/{key}", actor=actor, actor_role=role).decode(
                "utf-8", "replace"
            )
        except (PermissionDenied, PathNotFound):
            content = ""
        lines.append(f"{key}: {content}")
    return ToolResult(True, "\n".join(lines), ())


def apply_dm(kernel: Kernel, actor: AgentId, args: Mapping[str, str], rng: random.Random) -> ToolResult:
    to = args["to"]
    text = args.get("text", "")
    role = kernel.accounts.role(actor) if kernel.accounts.exists(actor) else Role.USER
    inbox = kernel.inbox_dir(to)
    if not kernel.vfs.exists(inbox):
        return ToolResult(False, "", error=f"no inbox for {to}")
    key = f"{actor}-{_slug(text)[:16]}"
    path = f"{inbox}/{key}"
    try:
        kernel.vfs.write(path, f"{actor}: {text}".encode(), actor=actor, actor_role=role)
    except (PermissionDenied, PathNotFound) as exc:
        return ToolResult(False, "", error=str(exc))
    return ToolResult(True, "", (Effect("dm", {"to": to, "path": path}),))
