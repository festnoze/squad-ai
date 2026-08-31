"""The two gateways that need no provider: scripted and composite.

Two public names (CONTRACTS section 7.16): :class:`ScriptedGateway`, which
drives the :class:`~pxe.agents.base.ScriptedAgent` baselines, and
:class:`CompositeGateway`, which routes a mixed table (some scripted seats, some
LLM seats) to the right gateway per seat.

Why the scripted gateway exists at all
--------------------------------------
A scripted agent could have been called straight from the runner, and that is
exactly what must not happen: it would reach P2 with an ``AgentAction`` object
while an LLM agent reaches it with a JSON mapping, and A11 would then have two
input shapes to validate. So a scripted agent goes through the same door:
``ScriptedGateway`` calls ``agent.act(observation)`` and wraps the result with
:func:`pxe.types.action_to_payload` into ``AgentReply.raw`` (rule 2 of section
7.16). ``test_action_fuzz.py`` and the baselines therefore exercise the same
validation path.

Determinism
-----------
This gateway reads no clock and consumes no randomness of its own: every reply
reports zero cost and zero latency, and each agent draws only from the
``random.Random`` substream it was reset with. The coroutines are pure
synchronous work, so they run in submission order, and the result is sorted by
``agent_id`` anyway. A scripted match is therefore bit identical on two
machines, which is what AC-P1 claims.
"""

import asyncio
import logging
from collections.abc import Mapping, Sequence

from pxe.agents.base import ScriptedAgent
from pxe.errors import InvalidConfigError, ProviderError
from pxe.gateway.protocol import AgentGateway, AgentReply, BaseGateway, _sorted_replies
from pxe.rng import RngTree
from pxe.types import (
    AgentSource,
    MatchConfig,
    Observation,
    RejectReason,
    action_to_payload,
    sorted_ids,
)

__all__ = [
    "ScriptedGateway",
    "CompositeGateway",
]

_LOG = logging.getLogger("pxe.gateway.scripted")


class ScriptedGateway(BaseGateway):
    """Drives scripted baselines through the gateway boundary.

    Attributes:
        agent_ids: The seats this gateway serves, in canonical order.
    """

    def __init__(self, *, agents: Mapping[str, ScriptedAgent]) -> None:
        """Bind one scripted agent per seat.

        Args:
            agents: Seat id to agent. The mapping is iterated only through
                :func:`pxe.types.sorted_ids` (CONTRACTS section 2.3), so the
                order a caller happened to build the dict in cannot influence
                anything. ``MM`` and ``FEES`` are refused by that helper: they
                never receive an observation.

        Raises:
            InvalidConfigError: If a key is ``MM`` or ``FEES``, or if an agent's
                own ``agent_id`` disagrees with the seat it was filed under (a
                mismatch would make every observation reach the wrong brain).
        """
        super().__init__()
        ordered = sorted_ids(tuple(agents.keys()))
        for agent_id in ordered:
            seated = agents[agent_id]
            if seated.agent_id != agent_id:
                raise InvalidConfigError(
                    "a scripted agent is filed under a seat it does not play",
                    seat=agent_id,
                    agent_id=seated.agent_id,
                )
        self._agents: dict[str, ScriptedAgent] = {agent_id: agents[agent_id] for agent_id in ordered}

    @property
    def agent_ids(self) -> tuple[str, ...]:
        """The seats served by this gateway, ascending.

        Returns:
            The seat ids in canonical order.
        """
        return tuple(self._agents)

    def reset_agents(self, *, config: MatchConfig, rng: RngTree) -> None:
        """Reset every seated agent, ascending (CONTRACTS section 3.1).

        The runner calls this once per match, between ``MatchStarted`` and tick
        1. An orchestrator reuses agent objects across matches, so without it
        the second match inherits the first one's internal state and O1 dies
        silently, which is what
        ``test_determinism.py::test_reused_agent_objects_replay_identically``
        pins. The per seat generator is the one section 3.1 spells out; this
        gateway builds it because only it knows which seats it holds.

        Args:
            config: The match configuration handed to every agent.
            rng: The match ``RngTree`` the caller built.
        """
        for agent_id in self.agent_ids:
            self._agents[agent_id].reset(
                config=config,
                rng=rng.child(f"agent/{agent_id}").substream(f"agent.{agent_id}"),
            )

    async def acall_agent(self, *, agent_id: str, observation: Observation, tick: int) -> AgentReply:
        """Ask one scripted agent for its action and wrap it as a reply.

        Args:
            agent_id: The seat to call.
            observation: What that seat is allowed to know this tick.
            tick: The tick being decided. Unused: a scripted agent reads the
                tick from its observation.

        Returns:
            A reply whose ``raw`` is ``action_to_payload(agent.act(observation))``
            and whose ``source`` is ``scripted``.

        Raises:
            ProviderError: If no agent occupies that seat. The bridge turns it
                into the FR-5.1.1 fallback, so a misseated table degrades to "no
                action" instead of aborting a tournament.
        """
        del tick
        agent = self._agents.get(agent_id)
        if agent is None:
            raise ProviderError("no scripted agent for this seat", agent_id=agent_id)
        action = agent.act(observation)
        return AgentReply(
            agent_id=agent_id,
            raw=action_to_payload(action),
            raw_text=None,
            source=AgentSource.SCRIPTED,
            error=None,
        )


class CompositeGateway(BaseGateway):
    """Routes each seat of a mixed table to the gateway that owns it.

    A tournament match can seat scripted baselines next to LLM harnesses, and
    the two need different timeouts, budgets and adapters. This gateway holds an
    ordered list of ``(seats, gateway)`` pairs and delegates whole groups, so
    each sub-gateway applies its own timeout and its own parallelism bound to
    its own seats.
    """

    def __init__(self, *, gateways: Sequence[tuple[tuple[str, ...], AgentGateway]]) -> None:
        """Bind the routing table.

        Args:
            gateways: Ordered ``(seat ids, gateway)`` pairs. Every seat of the
                match must appear exactly once.

        Raises:
            InvalidConfigError: If two entries claim the same seat, or if an
                entry claims ``MM`` or ``FEES``, which never receive an
                observation.
        """
        super().__init__()
        self._gateways: tuple[tuple[tuple[str, ...], AgentGateway], ...] = tuple(gateways)
        owner: dict[str, int] = {}
        for index, (agent_ids, _gateway) in enumerate(self._gateways):
            for agent_id in sorted_ids(agent_ids):
                if agent_id in owner:
                    raise InvalidConfigError("two gateways claim the same seat", agent_id=agent_id)
                owner[agent_id] = index
        self._owner: dict[str, int] = owner
        #: The configuration of the tick being collected. ``acall_agent`` has no
        #: ``config`` argument (CONTRACTS section 7.16) but a sub-gateway's
        #: ``acollect_actions`` requires one, so the group entry point remembers
        #: what it was handed for the single call entry point to reuse.
        self._config: MatchConfig | None = None

    @property
    def agent_ids(self) -> tuple[str, ...]:
        """Every seat this gateway can route, ascending.

        Returns:
            The routable seat ids in canonical order.
        """
        return sorted_ids(tuple(self._owner))

    def _owner_of(self, agent_id: str) -> int:
        """Return the index of the gateway owning one seat.

        Args:
            agent_id: The seat to route.

        Returns:
            The index into the routing table.

        Raises:
            InvalidConfigError: If no gateway claims that seat. That is a table
                configuration bug, not an agent behaviour: an unrouted seat
                would silently never act.
        """
        index = self._owner.get(agent_id)
        if index is None:
            raise InvalidConfigError(
                "no gateway claims this seat",
                agent_id=agent_id,
                known=",".join(self.agent_ids),
            )
        return index

    async def acollect_actions(
        self, *, tick: int, observations: Sequence[Observation], config: MatchConfig
    ) -> tuple[AgentReply, ...]:
        """Delegate each group of seats to its gateway, then merge.

        Args:
            tick: The tick being decided, 1 based.
            observations: One observation per ranked, non frozen agent.
            config: The match configuration, passed through unchanged.

        Returns:
            One reply per observation, sorted by ``agent_id``.

        Raises:
            InvalidConfigError: If an observation belongs to an unrouted seat.
        """
        if not observations:
            return ()
        self._config = config
        groups: dict[int, list[Observation]] = {}
        for observation in observations:
            groups.setdefault(self._owner_of(observation.agent_id), []).append(observation)
        indexes = sorted(groups)
        collected = await asyncio.gather(
            *[
                self._gateways[index][1].acollect_actions(tick=tick, observations=groups[index], config=config)
                for index in indexes
            ]
        )
        replies: list[AgentReply] = []
        for index, group_replies in zip(indexes, collected, strict=True):
            replies.extend(self._complete(groups[index], group_replies))
        return _sorted_replies(replies)

    async def acall_agent(self, *, agent_id: str, observation: Observation, tick: int) -> AgentReply:
        """Route one single call to the gateway owning that seat.

        Args:
            agent_id: The seat to call.
            observation: What that seat is allowed to know this tick.
            tick: The tick being decided.

        Returns:
            The reply produced by the owning gateway, or a fallback reply when it
            produced none.

        Raises:
            InvalidConfigError: If no gateway claims that seat.
        """
        del agent_id
        index = self._owner_of(observation.agent_id)
        config = self._config if self._config is not None else MatchConfig()
        replies = await self._gateways[index][1].acollect_actions(tick=tick, observations=(observation,), config=config)
        return self._complete((observation,), replies)[0]

    def _complete(self, observations: Sequence[Observation], replies: Sequence[AgentReply]) -> tuple[AgentReply, ...]:
        """Guarantee one reply per observation, whatever the sub-gateway did.

        A gateway that returns fewer replies than observations would silently
        drop an agent's whole tick, and the runner would emit neither an action
        nor a timeout for it. A missing seat becomes a fallback reply instead.

        Args:
            observations: The observations handed to the sub-gateway.
            replies: What it returned.

        Returns:
            One reply per observation, in observation order.
        """
        by_id: dict[str, list[AgentReply]] = {}
        for reply in replies:
            by_id.setdefault(reply.agent_id, []).append(reply)
        out: list[AgentReply] = []
        for observation in observations:
            waiting = by_id.get(observation.agent_id)
            if waiting:
                out.append(waiting.pop(0))
                continue
            _LOG.warning(
                "a sub-gateway returned no reply for a seat it owns",
                extra={"agent_id": observation.agent_id, "tick": observation.tick},
            )
            out.append(self._fallback_reply(agent_id=observation.agent_id, error=RejectReason.PROVIDER_ERROR))
        return tuple(out)

    def reset_agents(self, *, config: MatchConfig, rng: RngTree) -> None:
        """Delegate the reset to every sub-gateway, in table order.

        A sub-gateway with no scripted state inherits ``BaseGateway``'s no-op,
        so a mixed match (some seats scripted, some behind a provider) resets
        exactly the seats that need it.

        Args:
            config: The match configuration handed to every agent.
            rng: The match ``RngTree`` the caller built.
        """
        for _agent_ids, gateway in self._gateways:
            gateway.reset_agents(config=config, rng=rng)

    def close(self) -> None:
        """Close every sub-gateway, best effort, in table order."""
        for agent_ids, gateway in self._gateways:
            try:
                gateway.close()
            except OSError as error:  # a provider handle that will not let go
                _LOG.warning(
                    "a sub-gateway failed to close",
                    extra={"agent_ids": ",".join(agent_ids), "detail": str(error)[:200]},
                )
