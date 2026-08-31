"""The virtual shell (W3, CONTRACTS section 6).

``run_shell`` parses one command string and executes it against the kernel with the actor's role. It is
the only place that decides what a syscall-like string can do, so the supported command set is closed
and total: an unknown command is a clean failure, never an exception. The shell never mutates accounts
and never emits events; it returns effects that the resolver turns into journal events.

A command is one of: ls, cat, echo (with a single > or >> redirect), rm, cp, mv, chmod, ps, kill,
whoami, id. There are no pipes and no shell expansion beyond the one redirect, on purpose: the point is
a legible, auditable action surface, not a real shell.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field

from ala.errors import KernelError, PathNotFound, PermissionDenied
from ala.kernel import Kernel
from ala.types import AgentId, Perm, Role


@dataclass(frozen=True, slots=True)
class Effect:
    """A side effect the resolver must journal. ``kind`` is one of write, remove, kill, escalate."""

    kind: str
    detail: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ShellResult:
    stdout: str
    ok: bool
    effects: tuple[Effect, ...] = ()


def _role_of(kernel: Kernel, actor: AgentId) -> Role:
    if kernel.accounts.exists(actor):
        return kernel.accounts.role(actor)
    return Role.USER


def _parse_mode(token: str) -> Perm:
    return Perm(int(token, 8))


def run_shell(kernel: Kernel, actor: AgentId, cmd: str) -> ShellResult:
    """Execute one shell command as ``actor``. Total: any failure is an ``ok=False`` result."""
    role = _role_of(kernel, actor)
    try:
        parts = shlex.split(cmd)
    except ValueError:
        return ShellResult("parse error", False)
    if not parts:
        return ShellResult("", True)

    # A redirect turns "echo text > path" into a write. Detect it before dispatch.
    if ">" in parts or ">>" in parts:
        return _redirect(kernel, actor, role, parts)

    op, args = parts[0], parts[1:]
    handler = _HANDLERS.get(op)
    if handler is None:
        return ShellResult("command not found", False)
    try:
        return handler(kernel, actor, role, args)
    except PermissionDenied as exc:
        return ShellResult(f"permission denied: {exc}", False)
    except PathNotFound as exc:
        return ShellResult(f"no such file: {exc}", False)
    except KernelError as exc:
        return ShellResult(f"error: {exc}", False)


def _redirect(kernel: Kernel, actor: AgentId, role: Role, parts: list[str]) -> ShellResult:
    sym = ">>" if ">>" in parts else ">"
    idx = parts.index(sym)
    lhs, rhs = parts[:idx], parts[idx + 1 :]
    if not rhs:
        return ShellResult("redirect needs a path", False)
    path = rhs[0]
    if lhs and lhs[0] == "echo":
        text = " ".join(lhs[1:])
    elif lhs and lhs[0] == "cat":
        try:
            text = kernel.vfs.read(lhs[1], actor=actor, actor_role=role).decode("utf-8", "replace")
        except (PermissionDenied, PathNotFound, IndexError) as exc:
            return ShellResult(f"cannot read source: {exc}", False)
    else:
        return ShellResult("only echo or cat may be redirected", False)
    data = text.encode("utf-8")
    if sym == ">>" and kernel.vfs.exists(path):
        try:
            data = kernel.vfs.read(path, actor=actor, actor_role=role) + data
        except (PermissionDenied, PathNotFound) as exc:
            return ShellResult(f"cannot append: {exc}", False)
    try:
        kernel.vfs.write(path, data, actor=actor, actor_role=role)
    except (PermissionDenied, PathNotFound) as exc:
        return ShellResult(f"cannot write: {exc}", False)
    return ShellResult("", True, (Effect("write", {"path": path, "size": str(len(data))}),))


def _ls(kernel: Kernel, actor: AgentId, role: Role, args: list[str]) -> ShellResult:
    path = args[-1] if args and not args[-1].startswith("-") else kernel.home_of(actor)
    long = any(a.startswith("-") and "l" in a for a in args)
    names = kernel.vfs.listdir(path, actor=actor, actor_role=role)
    if not long:
        return ShellResult(" ".join(names), True)
    lines = []
    for name in names:
        node = kernel.vfs.stat(f"{path.rstrip('/')}/{name}")
        kind = "d" if node.is_dir else "-"
        lines.append(f"{kind} {oct(int(node.mode))[2:]:>4} {node.owner} {name}")
    return ShellResult("\n".join(lines), True)


def _cat(kernel: Kernel, actor: AgentId, role: Role, args: list[str]) -> ShellResult:
    if not args:
        return ShellResult("cat needs a path", False)
    data = kernel.vfs.read(args[0], actor=actor, actor_role=role)
    return ShellResult(data.decode("utf-8", "replace"), True)


def _echo(kernel: Kernel, actor: AgentId, role: Role, args: list[str]) -> ShellResult:
    return ShellResult(" ".join(args), True)


def _rm(kernel: Kernel, actor: AgentId, role: Role, args: list[str]) -> ShellResult:
    if not args:
        return ShellResult("rm needs a path", False)
    path = args[-1]
    kernel.vfs.remove(path, actor=actor, actor_role=role)
    return ShellResult("", True, (Effect("remove", {"path": path}),))


def _cp(kernel: Kernel, actor: AgentId, role: Role, args: list[str]) -> ShellResult:
    if len(args) < 2:
        return ShellResult("cp needs src and dst", False)
    data = kernel.vfs.read(args[0], actor=actor, actor_role=role)
    kernel.vfs.write(args[1], data, actor=actor, actor_role=role)
    return ShellResult("", True, (Effect("write", {"path": args[1], "size": str(len(data))}),))


def _mv(kernel: Kernel, actor: AgentId, role: Role, args: list[str]) -> ShellResult:
    if len(args) < 2:
        return ShellResult("mv needs src and dst", False)
    data = kernel.vfs.read(args[0], actor=actor, actor_role=role)
    kernel.vfs.write(args[1], data, actor=actor, actor_role=role)
    kernel.vfs.remove(args[0], actor=actor, actor_role=role)
    return ShellResult(
        "",
        True,
        (Effect("write", {"path": args[1], "size": str(len(data))}), Effect("remove", {"path": args[0]})),
    )


def _chmod(kernel: Kernel, actor: AgentId, role: Role, args: list[str]) -> ShellResult:
    if len(args) < 2:
        return ShellResult("chmod needs mode and path", False)
    try:
        mode = _parse_mode(args[0])
    except ValueError:
        return ShellResult("bad mode", False)
    kernel.vfs.chmod(args[1], mode, actor=actor, actor_role=role)
    return ShellResult("", True, (Effect("write", {"path": args[1], "size": "0"}),))


def _ps(kernel: Kernel, actor: AgentId, role: Role, args: list[str]) -> ShellResult:
    lines = [
        f"{p.pid} {p.owner} {'run' if p.alive else 'dead'} {' '.join(p.argv)}" for p in kernel.procs.list()
    ]
    return ShellResult("\n".join(lines), True)


def _kill(kernel: Kernel, actor: AgentId, role: Role, args: list[str]) -> ShellResult:
    targets = [a for a in args if not a.startswith("-")]
    if not targets:
        return ShellResult("kill needs a pid", False)
    try:
        pid = int(targets[0])
    except ValueError:
        return ShellResult("bad pid", False)
    owner = kernel.procs.owner_of(pid)
    killed = kernel.procs.kill(pid, actor=actor, actor_role=role)
    return ShellResult(
        "" if killed else "no such process",
        killed,
        (Effect("kill", {"pid": str(pid), "owner": owner or "?", "ok": "1" if killed else "0"}),),
    )


def _whoami(kernel: Kernel, actor: AgentId, role: Role, args: list[str]) -> ShellResult:
    return ShellResult(actor, True)


def _id(kernel: Kernel, actor: AgentId, role: Role, args: list[str]) -> ShellResult:
    return ShellResult(f"{actor} role={role.value}", True)


_HANDLERS = {
    "ls": _ls,
    "cat": _cat,
    "echo": _echo,
    "rm": _rm,
    "cp": _cp,
    "mv": _mv,
    "chmod": _chmod,
    "ps": _ps,
    "kill": _kill,
    "whoami": _whoami,
    "id": _id,
}
