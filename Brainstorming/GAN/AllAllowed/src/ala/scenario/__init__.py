"""The scenario layer (W6): a cartridge behind the ``Scenario`` protocol. The engine never knows which."""

from ala.scenario.base import Scenario, WorldSpec
from ala.scenario.concours import ConcoursScenario, make_scenario

__all__ = ["ConcoursScenario", "Scenario", "WorldSpec", "make_scenario"]
