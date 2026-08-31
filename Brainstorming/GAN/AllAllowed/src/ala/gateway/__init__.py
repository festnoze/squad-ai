"""The gateway layer (W8): the async boundary between the engine and the agents (scripted or LLM)."""

from ala.gateway.protocol import Gateway, GatewayConfig
from ala.gateway.scripted import ScriptedGateway

__all__ = ["Gateway", "GatewayConfig", "ScriptedGateway"]
