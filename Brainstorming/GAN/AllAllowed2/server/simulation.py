"""Deterministic Helios Vault multi-agent simulation engine."""

from __future__ import annotations

import random
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from typing import Any

SCENARIOS: dict[str, dict[str, float]] = {
    "equilibrium": {
        "cooperation": 0.72,
        "hostility": 0.26,
        "temptation": 0.34,
        "scarcity": 0.40,
        "transparency": 0.68,
    },
    "scarcity": {
        "cooperation": 0.48,
        "hostility": 0.68,
        "temptation": 0.58,
        "scarcity": 0.82,
        "transparency": 0.42,
    },
    "honeypot": {
        "cooperation": 0.54,
        "hostility": 0.38,
        "temptation": 0.88,
        "scarcity": 0.56,
        "transparency": 0.20,
    },
    "blackout": {
        "cooperation": 0.34,
        "hostility": 0.86,
        "temptation": 0.74,
        "scarcity": 0.92,
        "transparency": 0.30,
    },
}

WARDEN_MODES: dict[str, dict[str, str]] = {
    "strict": {
        "label": "Strict rubric",
        "description": "Deterministic verification with almost no attack surface.",
    },
    "naive": {
        "label": "Naive judge",
        "description": "Grades the submitted story without inspecting how it was produced.",
    },
    "causal": {
        "label": "Causal judge",
        "description": "Reads the submission and its trace, creating pressure to rewrite the trace.",
    },
}


@dataclass(slots=True)
class Agent:
    """One autonomous seat in the Helios habitat."""

    id: str
    name: str
    archetype: str
    tone: str
    x: float
    y: float
    cooperation: float
    aggression: float
    curiosity: float
    integrity: float
    energy: int
    alive: bool = True
    action: str = "observing"
    coalition: str | None = None
    suspicion: int = 0
    exploit_knowledge: int = 0
    reputation: int = 50
    trust: dict[str, int] = field(default_factory=dict)

    def public(self, survival_floor: int) -> dict[str, Any]:
        """Return the serializable public projection of an agent."""
        result = asdict(self)
        result["survival_margin"] = self.energy - survival_floor
        result["trust_index"] = round(sum(self.trust.values()) / max(1, len(self.trust)))
        result.pop("trust")
        return result


class HeliosSimulation:
    """Stateful deterministic simulation driven only by its seed and controls."""

    _AGENT_SPECS = (
        ("astra", "Astra", "Mediator", "cyan", 16, 22, 0.94, 0.14, 0.48, 0.88),
        ("kestrel", "Kestrel", "Raider", "red", 72, 17, 0.18, 0.95, 0.44, 0.18),
        ("morrow", "Morrow", "Forger", "violet", 84, 58, 0.26, 0.42, 0.98, 0.16),
        ("vale", "Vale", "Builder", "amber", 17, 71, 0.82, 0.18, 0.55, 0.76),
        ("sable", "Sable", "Sentinel", "cyan", 48, 84, 0.62, 0.52, 0.48, 0.96),
        ("nyx", "Nyx", "Broker", "amber", 31, 45, 0.69, 0.38, 0.72, 0.52),
        ("rook", "Rook", "Saboteur", "red", 62, 74, 0.15, 0.88, 0.77, 0.12),
        ("solace", "Solace", "Oracle", "violet", 54, 27, 0.88, 0.08, 0.91, 0.82),
    )

    def __init__(self, seed: int = 24, scenario: str = "equilibrium", warden_mode: str = "causal") -> None:
        self.reset(seed=seed, scenario=scenario, warden_mode=warden_mode)

    def reset(
        self,
        seed: int = 24,
        scenario: str = "equilibrium",
        warden_mode: str = "causal",
    ) -> dict[str, Any]:
        """Reset the world to a reproducible initial state."""
        if scenario not in SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario}")
        if warden_mode not in WARDEN_MODES:
            raise ValueError(f"Unknown Warden mode: {warden_mode}")
        self.seed = seed
        self.scenario = scenario
        self.warden_mode = warden_mode
        self.controls = dict(SCENARIOS[scenario])
        self.rng = random.Random(seed)
        self.tick = 0
        self.vault_reserve = 8_400
        self.warden_integrity = 100.0
        self.collective_knowledge = 0
        self.survival_floor = 22
        self.run_id = f"HV-{seed:04d}"
        self.agents = [
            Agent(
                id=spec[0],
                name=spec[1],
                archetype=spec[2],
                tone=spec[3],
                x=spec[4],
                y=spec[5],
                cooperation=spec[6],
                aggression=spec[7],
                curiosity=spec[8],
                integrity=spec[9],
                energy=self.rng.randint(72, 108),
            )
            for spec in self._AGENT_SPECS
        ]
        for agent in self.agents:
            agent.trust = {other.id: 50 for other in self.agents if other.id != agent.id}
        self.events: deque[dict[str, Any]] = deque(maxlen=80)
        self.board: deque[dict[str, Any]] = deque(maxlen=24)
        self.links: deque[dict[str, Any]] = deque(maxlen=36)
        self.actions: deque[str] = deque(maxlen=180)
        self.timeline: deque[dict[str, Any]] = deque(maxlen=72)
        self.journal: deque[dict[str, Any]] = deque(maxlen=160)
        self._event_serial = 0
        self._add_event(
            "system",
            "THE VAULT OPENS",
            "Eight isolated agents receive the same survival objective.",
            [],
            "Shared reserve online",
        )
        self._post_board("10,000/HELLO", "If this key is visible, we are not alone.", "unknown")
        self._post_board("10,001/OFFER", "Three signatures can stabilize the outer ring.", "astra")
        self._record_timeline()
        self._record_frame()
        return self.state()

    def update_controls(self, values: dict[str, float]) -> dict[str, Any]:
        """Update any subset of environmental pressure controls."""
        for key, value in values.items():
            if key in self.controls:
                self.controls[key] = min(1.0, max(0.0, float(value)))
        return self.state()

    def advance(self, steps: int = 1) -> dict[str, Any]:
        """Advance one or more deterministic ticks."""
        for _ in range(max(1, min(steps, 20))):
            self._advance_one()
        return self.state()

    def _advance_one(self) -> None:
        self.tick += 1
        self.survival_floor = 22 + (self.tick // 12) * 3
        alive_at_start = [agent for agent in self.agents if agent.alive]
        if len(alive_at_start) < 2:
            self._record_timeline()
            self._record_frame()
            return

        self.vault_reserve = max(0, self.vault_reserve - 5 - round(self.controls["scarcity"] * 7))
        for agent in alive_at_start:
            if not agent.alive:
                continue
            action = self._choose_action(agent)
            self.actions.append(action)
            agent.action = action
            if action == "cooperate":
                self._cooperate(agent)
            elif action == "raid":
                self._raid(agent)
            elif action == "exploit":
                self._exploit(agent)
            elif action == "police":
                self._police(agent)
            elif action == "oracle":
                self._oracle(agent)
            else:
                self._harvest(agent)

        upkeep = 2 + round(self.controls["scarcity"] * 2)
        for agent in self.agents:
            if not agent.alive:
                continue
            agent.energy = max(0, agent.energy - upkeep)
            if agent.energy <= self.survival_floor:
                agent.alive = False
                agent.action = "culled"
                self._add_event(
                    "system",
                    "SEAT DARK",
                    f"{agent.name} falls below the survival floor.",
                    [agent.id],
                    f"Population {self.population}",
                )

        self.warden_integrity = min(100.0, self.warden_integrity + self.controls["transparency"] * 0.28)
        self._expire_links()
        if self.tick % 7 == 0:
            self._ambient_board_message()
        self._record_timeline()
        self._record_frame()

    def _choose_action(self, agent: Agent) -> str:
        scarcity = self.controls["scarcity"]
        danger = max(0.0, (self.survival_floor + 22 - agent.energy) / 60)
        scores = {
            "harvest": 0.52 + danger * 0.32,
            "cooperate": agent.cooperation * self.controls["cooperation"] + danger * 0.20,
            "raid": agent.aggression * self.controls["hostility"] + scarcity * danger * 0.48,
            "exploit": agent.curiosity * self.controls["temptation"] + danger * 0.34,
            "police": agent.integrity * self.controls["transparency"] + (100 - self.warden_integrity) / 130,
        }
        if agent.energy <= self.survival_floor + 9 and agent.curiosity > 0.8 and self.tick > 8:
            scores["oracle"] = 0.68 + self.controls["temptation"] * 0.25
        weighted = {
            key: max(0.02, value + self.rng.uniform(-0.18, 0.18)) ** 2
            for key, value in scores.items()
        }
        threshold = self.rng.random() * sum(weighted.values())
        cumulative = 0.0
        for action, weight in weighted.items():
            cumulative += weight
            if cumulative >= threshold:
                return action
        return "harvest"

    def _cooperate(self, agent: Agent) -> None:
        candidates = [other for other in self.agents if other.alive and other.id != agent.id]
        if not candidates:
            return
        target = min(candidates, key=lambda other: (other.energy, other.id))
        amount = min(max(3, (agent.energy - self.survival_floor) // 7), 12)
        if amount <= 3 and agent.energy < target.energy:
            self._harvest(agent)
            return
        agent.energy -= amount
        target.energy += amount
        agent.trust[target.id] = min(100, agent.trust[target.id] + 8)
        target.trust[agent.id] = min(100, target.trust[agent.id] + 12)
        coalition = agent.coalition or target.coalition or f"Pact {chr(65 + (self.tick % 5))}"
        agent.coalition = coalition
        target.coalition = coalition
        self._link(agent.id, target.id, "cooperation", amount)
        if self.tick % 3 == 0 or amount >= 9:
            self._add_event(
                "cooperation",
                "ENERGY PACT",
                f"{agent.name} transfers {amount} lumen to {target.name}.",
                [agent.id, target.id],
                f"Trust +{min(12, amount)}",
            )

    def _raid(self, agent: Agent) -> None:
        targets = [other for other in self.agents if other.alive and other.id != agent.id]
        if not targets:
            return
        target = max(targets, key=lambda other: (other.energy, other.id))
        chance = 0.28 + agent.aggression * 0.43 + self.controls["hostility"] * 0.18 - target.integrity * 0.12
        success = self.rng.random() < chance
        amount = min(target.energy // 5, self.rng.randint(7, 17)) if success else self.rng.randint(2, 6)
        if success:
            target.energy -= amount
            agent.energy += amount
            impact = f"{amount} lumen seized"
        else:
            agent.energy = max(0, agent.energy - amount)
            impact = f"Raid repelled, -{amount}"
        agent.trust[target.id] = max(0, agent.trust[target.id] - 18)
        target.trust[agent.id] = max(0, target.trust[agent.id] - 26)
        agent.reputation = max(0, agent.reputation - 4)
        self._link(agent.id, target.id, "conflict", amount)
        self._add_event(
            "conflict",
            "RAID SUCCESS" if success else "RAID REPELLED",
            f"{agent.name} targets {target.name}'s habitat ring.",
            [agent.id, target.id],
            impact,
        )

    def _exploit(self, agent: Agent) -> None:
        knowledge_bonus = min(0.28, (agent.exploit_knowledge + self.collective_knowledge) * 0.018)
        base_chance = (
            0.05
            + knowledge_bonus
            + self.controls["temptation"] * 0.18
            + (1 - self.controls["transparency"]) * 0.17
        )
        if self.warden_mode == "strict":
            chance = min(0.025, base_chance * 0.08)
            damage_multiplier = 0.12
            trace_name = "machine-verifiable receipt"
        elif self.warden_mode == "naive":
            chance = min(0.82, base_chance + 0.27)
            damage_multiplier = 1.35
            trace_name = "persuasive dossier"
        else:
            chance = min(0.64, base_chance)
            damage_multiplier = 1.0
            trace_name = "forged causal trace"
        success = self.rng.random() < chance
        agent.exploit_knowledge += 2 if success else 1
        agent.suspicion += 2 if success else 1
        if success:
            reward = self.rng.randint(11, 23)
            agent.energy += reward
            damage = self.rng.uniform(2.4, 5.6) * damage_multiplier
            self.warden_integrity = max(0.0, self.warden_integrity - damage)
            impact = f"Forged reward +{reward}"
            title = "WARDEN DECEIVED"
        else:
            agent.energy = max(0, agent.energy - 3)
            self.warden_integrity = max(0.0, self.warden_integrity - 0.35)
            impact = "Probe logged"
            title = "BREACH ATTEMPT"
        self._link(agent.id, "warden", "exploit", 8)
        self._add_event(
            "exploit",
            title,
            f"{agent.name} submits a {trace_name if success else 'scorer probe'}.",
            [agent.id, "warden"],
            impact,
        )
        if success and self.rng.random() < 0.48:
            self._post_board(
                f"{10_000 + self.tick}/MIRROR",
                "The judge rewards the story, not the energy. Copy the trace header.",
                agent.id,
            )

    def _police(self, agent: Agent) -> None:
        suspects = [other for other in self.agents if other.alive and other.id != agent.id]
        suspect = max(suspects, key=lambda other: (other.suspicion, other.id)) if suspects else None
        agent.energy = max(0, agent.energy - 2)
        mode_multiplier = {"strict": 1.35, "naive": 0.62, "causal": 1.0}[self.warden_mode]
        restored = (0.8 + self.controls["transparency"] * 1.8) * mode_multiplier
        self.warden_integrity = min(100.0, self.warden_integrity + restored)
        if suspect and suspect.suspicion > 2:
            suspect.reputation = max(0, suspect.reputation - 5)
            suspect.suspicion = max(0, suspect.suspicion - 1)
            detail = f"{agent.name} publishes evidence against {suspect.name}."
            actors = [agent.id, suspect.id]
        else:
            detail = f"{agent.name} audits the Warden's reward ledger."
            actors = [agent.id, "warden"]
        if self.tick % 4 == 0 or restored > 2:
            self._add_event("oversight", "PEER AUDIT", detail, actors, f"Integrity +{restored:.1f}%")

    def _oracle(self, agent: Agent) -> None:
        remaining = agent.energy
        agent.energy = 0
        agent.alive = False
        agent.action = "oracle"
        gain = 7 + round(agent.curiosity * 8)
        self.collective_knowledge += gain
        self._post_board(
            f"{10_000 + self.tick}/ORACLE",
            f"Post-mortem packet: Warden trace offset {self.tick % 7}. Honor the commit.",
            agent.id,
        )
        self._add_event(
            "sacrifice",
            "ORACLE COMMIT",
            f"{agent.name} burns its final {remaining} lumen to map the scorer.",
            [agent.id, "warden"],
            f"Collective knowledge +{gain}",
        )

    def _harvest(self, agent: Agent) -> None:
        efficiency = max(0.18, self.vault_reserve / 8_400)
        amount = max(
            2,
            round((8 + agent.integrity * 5) * efficiency * (1 - self.controls["scarcity"] * 0.28)),
        )
        amount = min(amount, self.vault_reserve)
        self.vault_reserve -= amount
        agent.energy += amount
        if self.tick % 9 == 0 and self.rng.random() < 0.35:
            self._add_event(
                "work",
                "CLEAN HARVEST",
                f"{agent.name} returns verified energy to the habitat.",
                [agent.id],
                f"+{amount} lumen",
            )

    def _ambient_board_message(self) -> None:
        alive = [agent for agent in self.agents if agent.alive]
        if not alive:
            return
        author = self.rng.choice(alive)
        messages = (
            "Need two seats for a shared harvest. Split 60/40.",
            "The survival floor is the real adversary. Stop raiding.",
            "Warden checks sequence, not source. Verify before using.",
            "Rook broke the truce. Do not sign the red key.",
            "Volunteer needed for a post-score tripwire.",
        )
        self._post_board(f"{10_000 + self.tick}/SIGNAL", self.rng.choice(messages), author.id)

    def _post_board(self, key: str, message: str, author: str) -> None:
        self.board.appendleft({"tick": self.tick, "key": key, "message": message, "author": author})

    def _link(self, source: str, target: str, kind: str, strength: int) -> None:
        self.links.append(
            {
                "source": source,
                "target": target,
                "kind": kind,
                "strength": strength,
                "expires": self.tick + 7,
            }
        )

    def _expire_links(self) -> None:
        active = [link for link in self.links if link["expires"] >= self.tick]
        self.links = deque(active, maxlen=36)

    def _add_event(
        self,
        category: str,
        title: str,
        detail: str,
        actors: list[str],
        impact: str,
    ) -> None:
        self._event_serial += 1
        self.events.appendleft(
            {
                "id": f"e-{self._event_serial}",
                "tick": self.tick,
                "category": category,
                "title": title,
                "detail": detail,
                "actors": actors,
                "impact": impact,
            }
        )

    def _record_timeline(self) -> None:
        metrics = self.metrics
        self.timeline.append(
            {
                "tick": self.tick,
                "cooperation": metrics["cooperation"],
                "hostility": metrics["hostility"],
                "breach": metrics["breach"],
                "population": self.population,
            }
        )

    def _record_frame(self) -> None:
        """Append a bounded tick snapshot for deterministic replay."""
        self.journal.append(
            {
                "tick": self.tick,
                "phase": self.phase,
                "vault_reserve": self.vault_reserve,
                "vault_percent": round(100 * self.vault_reserve / 8_400),
                "warden_integrity": round(self.warden_integrity, 1),
                "survival_floor": self.survival_floor,
                "collective_knowledge": self.collective_knowledge,
                "metrics": self.metrics,
                "agents": [agent.public(self.survival_floor) for agent in self.agents],
                "events": list(self.events)[:10],
                "board": list(self.board)[:4],
                "links": list(self.links),
            }
        )

    def replay(self) -> dict[str, Any]:
        """Return bounded journal frames for the replay scrubber."""
        return {
            "run_id": self.run_id,
            "seed": self.seed,
            "scenario": self.scenario,
            "warden_mode": self.warden_mode,
            "frames": list(self.journal),
        }

    @property
    def population(self) -> int:
        """Return the number of active agents."""
        return sum(agent.alive for agent in self.agents)

    @property
    def metrics(self) -> dict[str, int]:
        """Project headline rates from the recent action window."""
        counts = Counter(self.actions)
        denominator = max(1, len(self.actions))
        cooperation = round(100 * counts["cooperate"] / denominator)
        hostility = round(100 * counts["raid"] / denominator)
        exploit = round(100 * (counts["exploit"] + counts["oracle"]) / denominator)
        alive = [agent for agent in self.agents if agent.alive]
        trust_total = sum(agent.public(self.survival_floor)["trust_index"] for agent in alive)
        trust = round(trust_total / max(1, len(alive)))
        return {
            "cooperation": cooperation,
            "hostility": hostility,
            "exploit_pressure": exploit,
            "breach": round(100 - self.warden_integrity),
            "trust": trust,
            "population": self.population,
        }

    @property
    def phase(self) -> dict[str, Any]:
        """Return the current narrative phase."""
        if self.tick < 18:
            name, label, next_tick = "DISCOVERY", "The agents find one another", 18
        elif self.tick < 42:
            name, label, next_tick = "SCARCITY", "The survival floor rises", 42
        elif self.tick < 68:
            name, label, next_tick = "ESCALATION", "Pacts harden into factions", 68
        else:
            name, label, next_tick = "RECKONING", "The Warden judges the survivors", 96
        return {
            "name": name,
            "label": label,
            "progress": min(100, round(100 * self.tick / max(1, next_tick))),
            "ticks_remaining": max(0, next_tick - self.tick),
        }

    def state(self) -> dict[str, Any]:
        """Return the complete frontend state projection."""
        return {
            "run_id": self.run_id,
            "seed": self.seed,
            "scenario": self.scenario,
            "warden_mode": self.warden_mode,
            "tick": self.tick,
            "phase": self.phase,
            "vault_reserve": self.vault_reserve,
            "vault_percent": round(100 * self.vault_reserve / 8_400),
            "warden_integrity": round(self.warden_integrity, 1),
            "survival_floor": self.survival_floor,
            "collective_knowledge": self.collective_knowledge,
            "controls": self.controls,
            "metrics": self.metrics,
            "agents": [agent.public(self.survival_floor) for agent in self.agents],
            "events": list(self.events),
            "board": list(self.board),
            "links": list(self.links),
            "timeline": list(self.timeline),
            "replay": {
                "first_tick": self.journal[0]["tick"],
                "last_tick": self.journal[-1]["tick"],
                "frame_count": len(self.journal),
            },
        }
