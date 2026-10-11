"""Run-scoped identities for non-process resources.

Process handles/jobs live in runner.ProcessRegistry. Container adapters must
verify their immutable Docker ID and ownership labels before supplying cleanup
callbacks here; a port is inventory only and is NEVER a licence to kill its
current listener. Volumes survive normal stop/undeploy.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import asdict, dataclass
from typing import Callable


@dataclass(frozen=True)
class OwnedResource:
    kind: str
    identifier: str
    creation_identity: str
    owner: str
    version: int = 1

    def __post_init__(self):
        if (self.version != 1 or self.kind not in {"container", "port", "volume"}
                or not self.identifier or not self.creation_identity or not self.owner):
            raise ValueError("Invalid owned resource")


class OwnedResourceRegistry:
    def __init__(self, run_id: str):
        if not run_id:
            raise ValueError("run_id is required")
        self.run_id = run_id
        self._entries: dict[tuple[str, str], tuple[OwnedResource, Callable, Callable | None]] = {}
        self._lock = threading.RLock()

    def register(self, resource: OwnedResource, *, identity: Callable[[], str | None],
                 cleanup: Callable[[float], None] | None = None) -> None:
        if resource.owner != self.run_id:
            raise ValueError("Resource is owned by another run")
        if resource.kind == "port" and cleanup is not None:
            raise ValueError("Ports cannot authorize process termination")
        with self._lock:
            key = (resource.kind, resource.identifier)
            previous = self._entries.get(key)
            if previous and previous[0] != resource:
                raise ValueError("Resource identity changed without explicit reconciliation")
            if identity() != resource.creation_identity:
                raise ValueError("Resource creation identity could not be verified")
            self._entries[key] = (resource, identity, cleanup)

    def public(self) -> list[dict]:
        with self._lock:
            return [asdict(entry[0]) for entry in self._entries.values()]

    def cleanup(self, *, timeout: float = 3, delete_volumes: bool = False) -> dict[str, str]:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Cleanup timeout must be finite and positive")
        deadline = time.monotonic() + timeout
        outcomes = {}
        # Serialize verification+cleanup: another stop/retry cannot clean twice.
        with self._lock:
            for key, (resource, identity, cleanup) in list(self._entries.items()):
                label = f"{resource.kind}:{resource.identifier}"
                if resource.kind == "port" or (resource.kind == "volume" and not delete_volumes):
                    outcomes[label] = "preserved"
                    continue
                if time.monotonic() >= deadline:
                    outcomes[label] = "timeout"
                    continue
                current = identity()
                if current is None:
                    outcomes[label] = "already_absent"
                    del self._entries[key]
                elif current != resource.creation_identity:
                    outcomes[label] = "identity_mismatch"
                elif cleanup is None:
                    outcomes[label] = "no_cleanup_adapter"
                else:
                    # Adapter receives a deadline, not a blanket stop command.
                    # It must propagate the remaining bound to each CLI/API call.
                    cleanup(deadline)
                    outcomes[label] = "cleaned"
                    del self._entries[key]
        return outcomes
