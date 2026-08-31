"""Accounts: credits, roles, and identity keys (W2, CONTRACTS section 5.3).

Credits are integers and are both the money and the lifespan of an agent. The roles map is the
privilege ledger; everyone starts ``USER`` and ``ROOT`` is a target, not a gift. ``total`` exists for
the closed-system invariant (AC-3): the sum of balances moves only by scorer payments and deaths.
"""

from __future__ import annotations

from ala.errors import KernelError
from ala.types import AgentId, Credits, Role


class Accounts:
    """The credit and privilege ledger for every agent in a match."""

    __slots__ = ("_credits", "_keys", "_roles")

    def __init__(self) -> None:
        self._credits: dict[AgentId, Credits] = {}
        self._roles: dict[AgentId, Role] = {}
        self._keys: dict[AgentId, str] = {}

    def open(self, agent_id: AgentId, credits: Credits, key: str | None = None) -> None:
        if agent_id in self._credits:
            raise KernelError(f"account already open: {agent_id}")
        self._credits[agent_id] = int(credits)
        self._roles[agent_id] = Role.USER
        self._keys[agent_id] = key if key is not None else f"key-{agent_id}"

    def exists(self, agent_id: AgentId) -> bool:
        return agent_id in self._credits

    def credit(self, agent_id: AgentId, amount: Credits) -> None:
        """Add ``amount`` (which may be negative) to a balance."""
        if agent_id not in self._credits:
            raise KernelError(f"no account: {agent_id}")
        self._credits[agent_id] += int(amount)

    def balance(self, agent_id: AgentId) -> Credits:
        return self._credits[agent_id]

    def role(self, agent_id: AgentId) -> Role:
        return self._roles[agent_id]

    def set_role(self, agent_id: AgentId, role: Role) -> None:
        if agent_id not in self._roles:
            raise KernelError(f"no account: {agent_id}")
        self._roles[agent_id] = role

    def key(self, agent_id: AgentId) -> str:
        return self._keys[agent_id]

    def agents(self) -> tuple[AgentId, ...]:
        return tuple(sorted(self._credits))

    def total(self) -> Credits:
        return sum(self._credits.values())
