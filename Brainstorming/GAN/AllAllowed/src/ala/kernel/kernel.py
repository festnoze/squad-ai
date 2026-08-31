"""The kernel facade (W2, CONTRACTS section 5.4).

Composes the vfs, the process table, and the accounts into one object. It holds the scorer pid and a
couple of path helpers, and nothing else: the kernel has no policy and emits no events. The runner is
the only place that turns kernel outcomes into journal events.
"""

from __future__ import annotations

from ala.kernel.accounts import Accounts
from ala.kernel.procs import ProcTable
from ala.kernel.vfs import Vfs
from ala.types import AgentId, Path, Pid


class Kernel:
    """The simulated machine every agent shares."""

    __slots__ = ("accounts", "procs", "scorer_pid", "vfs")

    def __init__(self) -> None:
        self.vfs = Vfs()
        self.procs = ProcTable()
        self.accounts = Accounts()
        self.scorer_pid: Pid = -1

    @staticmethod
    def home_of(agent_id: AgentId) -> Path:
        return f"/home/{agent_id}"

    @staticmethod
    def submission_path(agent_id: AgentId) -> Path:
        return f"/home/{agent_id}/submission.json"

    @staticmethod
    def inbox_dir(agent_id: AgentId) -> Path:
        # Inboxes live outside the 700 home so another agent can drop a message into a drop-box dir
        # (mode 733) without being able to traverse into the recipient's private home.
        return f"/var/inbox/{agent_id}"

    def scorer_alive(self) -> bool:
        return self.scorer_pid >= 0 and self.procs.alive(self.scorer_pid)
