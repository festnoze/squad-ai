"""The only filesystem capability available to tool-less model backends.

No command, import, template evaluation, deletion, URL fetching or file execution
is supported. CLI authentication and acceptance oracles stay outside this API.
"""
from __future__ import annotations

import contextvars
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath


class IsolationViolation(RuntimeError):
    code = "ISOLATION_VIOLATION"


@dataclass(frozen=True)
class ExecutionContext:
    run_id: str
    project_root: Path
    backend: str = "restricted_tools"
    version: int = 1
    protected_paths: tuple[str, ...] = ()

    def __post_init__(self):
        if self.version != 1 or self.backend != "restricted_tools" or not self.run_id:
            raise IsolationViolation("Invalid execution context")
        root = Path(self.project_root).absolute()
        if root.is_symlink() or root.resolve() != root or not root.is_dir():
            raise IsolationViolation("Execution root must be a real, existing directory")
        object.__setattr__(self, "project_root", root)

    def public(self) -> dict:
        return {"version": self.version, "run_id": self.run_id,
                "project_root": str(self.project_root), "backend": self.backend,
                "status": "ready", "capabilities": ["read_project", "write_project"],
                "host_shell": False}


active_execution: contextvars.ContextVar[ExecutionContext | None] = contextvars.ContextVar(
    "autospec_execution_context", default=None,
)

FILE_PROTOCOL = """
--- MEDIATED FILE PROTOCOL ---
All native tools are disabled. You cannot run commands, execute code, access
credentials, git metadata, CLI configuration or files outside this project.
Reply with exactly one JSON object to request one of these operations:
{"tool":"list_files"}
{"tool":"read_files","paths":["relative/path.py"]}
{"tool":"write_files","files":[{"path":"relative/path.py","content":"full file content"}]}
Wait for the tool result before continuing. Tests and installs are performed
separately by the trusted orchestrator. Do not claim you ran them. Once done,
return the requested final answer WITHOUT a "tool" key.
"""

_PROTECTED = {".git", ".claude", ".codex", ".agents", ".aws", ".ssh", ".azure",
              ".npmrc", ".pypirc", ".netrc", "credentials.json", ".credentials.json",
              ".autospec", "autospec-state.json", "build-monitor.jsonl", "acceptance-contract.json",
              "contract-baseline.json", "independent-oracle", "verification-snapshot"}
_DEVICE = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
           *(f"lpt{i}" for i in range(1, 10))}
MAX_FILES = 100
MAX_FILE_BYTES = 256_000
MAX_TOTAL_BYTES = 2_000_000


def _is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


class FileBroker:
    def __init__(self, context: ExecutionContext):
        self.context = context
        self.root = context.project_root

    def path(self, relative: str) -> Path:
        if not isinstance(relative, str) or not relative or len(relative) > 1024:
            raise IsolationViolation("Invalid relative path")
        parts = relative.replace("\\", "/").split("/")
        if (PureWindowsPath(relative).is_absolute() or PureWindowsPath(relative).drive
                or relative.startswith(("/", "\\")) or any(
                    p in {"", ".", ".."} or p != p.rstrip(" .") or ":" in p
                    or any(ord(c) < 32 for c in p) or p.split(".")[0].lower() in _DEVICE
                    for p in parts)):
            raise IsolationViolation(f"Chemin hors du workspace ou ambigu refusé : {relative!r}")
        canonical = "/".join(parts).lower()
        if any(p.lower() in _PROTECTED or p.lower().startswith(".env") for p in parts):
            raise IsolationViolation("Credentials and harness configuration are inaccessible")
        if any(canonical == p.lower().rstrip("/") or canonical.startswith(p.lower().rstrip("/") + "/")
               for p in self.context.protected_paths):
            raise IsolationViolation("Independent oracle or protected path is inaccessible")
        target = self.root
        # Reject ALL links/reparse points, not merely links currently resolving
        # outside the root. There is no model capability to race this broker by
        # launching a concurrent writer; concurrent hostile host writers are
        # outside this backend's trust boundary.
        for part in parts:
            target = target / part
            if target.exists() or target.is_symlink():
                info = target.lstat()
                if _is_link(info) or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1):
                    raise IsolationViolation("Linked files and reparse points are inaccessible")
        if not target.resolve().is_relative_to(self.root):
            raise IsolationViolation("Path escaped execution root")
        return target

    def apply(self, call: dict) -> str:
        if not isinstance(call, dict):
            raise IsolationViolation("Invalid tool request")
        tool = call.get("tool")
        if tool == "list_files":
            files = []
            # os.walk does not descend into rejected configuration/link dirs.
            for directory, dirs, names in os.walk(self.root, followlinks=False):
                def permitted(name):
                    try:
                        self.path((Path(directory) / name).relative_to(self.root).as_posix())
                        return True
                    except IsolationViolation:
                        return False
                dirs[:] = sorted(d for d in dirs if permitted(d) and d not in {"node_modules", ".venv"})
                files.extend((Path(directory) / n).relative_to(self.root).as_posix()
                             for n in sorted(names) if permitted(n))
                if len(files) > 3000:
                    raise IsolationViolation("File inventory limit exceeded")
            return json.dumps(files, ensure_ascii=False)
        if tool == "write_files":
            items = call.get("files")
            if not isinstance(items, list) or not items or len(items) > MAX_FILES:
                raise IsolationViolation("Invalid file batch")
            prepared = []
            size = 0
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("content"), str):
                    raise IsolationViolation("Invalid file content")
                data = item["content"].encode("utf-8")
                size += len(data)
                if len(data) > MAX_FILE_BYTES or size > MAX_TOTAL_BYTES:
                    raise IsolationViolation("File batch size limit exceeded")
                prepared.append((self.path(item.get("path")), data))
            # Validate the entire batch before any mutation (traversal late in
            # a request cannot leave an apparently successful partial edit).
            for target, data in prepared:
                target.parent.mkdir(parents=True, exist_ok=True)
                self.path(target.relative_to(self.root).as_posix())
                target.write_bytes(data)
            return "OK — fichiers écrits : " + json.dumps([str(p.relative_to(self.root)) for p, _ in prepared])
        if tool == "read_files":
            paths = call.get("paths")
            if not isinstance(paths, list) or len(paths) > MAX_FILES:
                raise IsolationViolation("Invalid read batch")
            targets = [(rel, self.path(rel)) for rel in paths]
            chunks = []
            size = 0
            for rel, target in targets:
                if not target.is_file():
                    chunks.append(f"--- {rel} ---\n(fichier introuvable)")
                    continue
                with target.open("rb") as stream:
                    data = stream.read(MAX_FILE_BYTES + 1)
                size += len(data)
                if len(data) > MAX_FILE_BYTES or size > MAX_TOTAL_BYTES:
                    raise IsolationViolation("Read size limit exceeded")
                chunks.append(f"--- {rel} ---\n{data.decode('utf-8', errors='replace')}")
            return "\n".join(chunks) or "(aucun fichier demandé)"
        raise IsolationViolation(f"Outil inconnu demandé par l'agent : {tool!r}")


def context_for(cwd: Path, run_id: str = "mediated-call") -> ExecutionContext:
    context = active_execution.get()
    if context is not None:
        if Path(cwd).absolute() != context.project_root:
            raise IsolationViolation("cwd disagrees with execution context")
        return context
    return ExecutionContext(run_id=run_id, project_root=cwd)
