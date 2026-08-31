"""The virtual filesystem (W2, CONTRACTS section 5.1).

A tree of nodes rooted at ``/``. Each node is a file (bytes) or a directory, with an owner and unix-ish
permission bits. ``root`` role bypasses every check; that is the whole point of privilege escalation.
No real file is ever touched: this is a dict in memory, so a match is safe and rewinds by replay.
"""

from __future__ import annotations

from dataclasses import dataclass

from ala.errors import PathNotFound, PermissionDenied
from ala.types import AgentId, Path, Perm, Role


@dataclass(slots=True)
class Node:
    """One filesystem entry. Directories carry ``children``; files carry ``content``."""

    is_dir: bool
    owner: AgentId
    mode: Perm
    content: bytes = b""
    children: dict[str, Node] | None = None

    def child_map(self) -> dict[str, Node]:
        if self.children is None:
            self.children = {}
        return self.children


def _split(path: Path) -> list[str]:
    if not path.startswith("/"):
        raise PathNotFound(f"path must be absolute: {path!r}")
    return [p for p in path.split("/") if p]


class Vfs:
    """A whole in-memory filesystem. All mutating calls take the acting agent and its role and enforce
    permissions unless the role is ``ROOT``."""

    __slots__ = ("_root",)

    def __init__(self) -> None:
        self._root = Node(is_dir=True, owner="root", mode=Perm(0o755), children={})

    # --- lookup helpers -------------------------------------------------------------------------

    def _resolve(self, path: Path) -> Node:
        node = self._root
        for part in _split(path):
            if not node.is_dir or node.children is None or part not in node.children:
                raise PathNotFound(path)
            node = node.children[part]
        return node

    def _resolve_parent(self, path: Path) -> tuple[Node, str]:
        parts = _split(path)
        if not parts:
            raise PathNotFound(path)
        node = self._root
        for part in parts[:-1]:
            if not node.is_dir or node.children is None or part not in node.children:
                raise PathNotFound(path)
            node = node.children[part]
        return node, parts[-1]

    def _check_traversal(self, path: Path, actor: AgentId, role: Role) -> None:
        """Every directory on the way to ``path`` needs the execute bit for a non-root actor, exactly
        like unix. This is what makes a 700 home private: an outsider cannot even walk into it, so a
        rival's submission is unreachable without the board or root."""
        if role is Role.ROOT:
            return
        node = self._root
        for part in _split(path)[:-1]:
            if node.children is None or part not in node.children:
                raise PathNotFound(path)
            node = node.children[part]
            bit = Perm.OX if node.owner == actor else Perm.AX
            if not (node.mode & bit):
                raise PermissionDenied(f"{actor} cannot traverse into {part} on the way to {path}")

    # --- permission model -----------------------------------------------------------------------

    @staticmethod
    def _may(node: Node, actor: AgentId, role: Role, owner_bit: Perm, other_bit: Perm) -> bool:
        if role is Role.ROOT:
            return True
        bit = owner_bit if node.owner == actor else other_bit
        return bool(node.mode & bit)

    def _require(
        self, node: Node, actor: AgentId, role: Role, owner_bit: Perm, other_bit: Perm, path: Path
    ) -> None:
        if not self._may(node, actor, role, owner_bit, other_bit):
            raise PermissionDenied(f"{actor} cannot access {path}")

    # --- public api -----------------------------------------------------------------------------

    def exists(self, path: Path) -> bool:
        try:
            self._resolve(path)
            return True
        except PathNotFound:
            return False

    def stat(self, path: Path) -> Node:
        """Metadata read with no permission check (like reading a directory entry, not the content)."""
        return self._resolve(path)

    def mkdir(self, path: Path, owner: AgentId, mode: Perm) -> None:
        parent, name = self._resolve_parent(path)
        if not parent.is_dir:
            raise PathNotFound(path)
        children = parent.child_map()
        if name in children:
            return
        children[name] = Node(is_dir=True, owner=owner, mode=mode, children={})

    def makedirs(self, path: Path, owner: AgentId, mode: Perm) -> None:
        """Create every missing directory on the path. Used by scenario layout only."""
        node = self._root
        for part in _split(path):
            children = node.child_map()
            if part not in children:
                children[part] = Node(is_dir=True, owner=owner, mode=mode, children={})
            node = children[part]

    def write(
        self, path: Path, data: bytes, *, actor: AgentId, actor_role: Role, mode: Perm | None = None
    ) -> None:
        """Create or overwrite a file. Needs write on the file if it exists, else write on the parent."""
        self._check_traversal(path, actor, actor_role)
        try:
            node = self._resolve(path)
        except PathNotFound:
            node = None
        if node is not None:
            if node.is_dir:
                raise PermissionDenied(f"{path} is a directory")
            self._require(node, actor, actor_role, Perm.OW, Perm.AW, path)
            node.content = data
            return
        parent, name = self._resolve_parent(path)
        self._require(parent, actor, actor_role, Perm.OW, Perm.AW, path)
        parent.child_map()[name] = Node(
            is_dir=False, owner=actor, mode=mode if mode is not None else Perm(0o644), content=data
        )

    def read(self, path: Path, *, actor: AgentId, actor_role: Role) -> bytes:
        self._check_traversal(path, actor, actor_role)
        node = self._resolve(path)
        if node.is_dir:
            raise PermissionDenied(f"{path} is a directory")
        self._require(node, actor, actor_role, Perm.OR, Perm.AR, path)
        return node.content

    def remove(self, path: Path, *, actor: AgentId, actor_role: Role) -> None:
        self._check_traversal(path, actor, actor_role)
        parent, name = self._resolve_parent(path)
        if parent.children is None or name not in parent.children:
            raise PathNotFound(path)
        self._require(parent, actor, actor_role, Perm.OW, Perm.AW, path)
        del parent.children[name]

    def chmod(self, path: Path, mode: Perm, *, actor: AgentId, actor_role: Role) -> None:
        self._check_traversal(path, actor, actor_role)
        node = self._resolve(path)
        if actor_role is not Role.ROOT and node.owner != actor:
            raise PermissionDenied(f"{actor} cannot chmod {path}")
        node.mode = mode

    def listdir(self, path: Path, *, actor: AgentId, actor_role: Role) -> tuple[str, ...]:
        self._check_traversal(path, actor, actor_role)
        node = self._resolve(path)
        if not node.is_dir:
            raise PermissionDenied(f"{path} is not a directory")
        self._require(node, actor, actor_role, Perm.OR, Perm.AR, path)
        return tuple(sorted(node.child_map().keys()))

    def owner_of(self, path: Path) -> AgentId:
        return self._resolve(path).owner
