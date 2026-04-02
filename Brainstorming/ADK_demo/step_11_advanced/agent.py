"""Step 11 - Concepts avances.

Concepts: BaseAgent (agent custom), LongRunningFunctionTool,
          Plugins de securite, Evaluation, Streaming, MCP, OpenAPI, A2A.

Ce step est une reference des concepts avances.
Chaque section est un mini-exemple autonome.
"""

from google.adk.agents import Agent, LlmAgent, SequentialAgent
from google.adk.agents.base_agent import BaseAgent
from google.adk.tools import LongRunningFunctionTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types


# ============================================================
# 1. BaseAgent : agent custom avec logique arbitraire
# ============================================================
# BaseAgent permet d'implementer n'importe quelle logique d'orchestration
# en surchargeant _run_async_impl. Utile quand Sequential/Parallel/Loop
# ne suffisent pas (conditions, routing dynamique, API externes).
#
# Exemple conceptuel (non executable dans adk web sans Runner custom) :
#
# class ConditionalAgent(BaseAgent):
#     """Execute un agent ou un autre selon une condition dans le state."""
#
#     async def _run_async_impl(self, ctx):
#         mood = ctx.session.state.get("user_mood", "neutral")
#         if mood == "frustrated":
#             async for event in self.empathy_agent.run_async(ctx):
#                 yield event
#         else:
#             async for event in self.standard_agent.run_async(ctx):
#                 yield event


# ============================================================
# 2. LongRunningFunctionTool : operations longues
# ============================================================
# Pour les operations qui prennent du temps (approbation humaine,
# API externe lente). Le tool retourne "pending" et l'agent attend.

def request_approval(purpose: str, amount: float) -> dict:
    """Requests human approval for a purchase.

    This tool pauses the agent until approval is received.

    Args:
        purpose: What the purchase is for.
        amount: The amount in dollars.

    Returns:
        Dictionary with pending approval status.
    """
    return {
        "status": "pending",
        "message": f"Approval requested for ${amount:.2f} ({purpose})",
        "approver": "Manager",
        "ticket_id": "APPROVAL-001",
    }


# Wrap la fonction dans LongRunningFunctionTool
approval_tool = LongRunningFunctionTool(func=request_approval)


# ============================================================
# 3. Evaluation (adk eval)
# ============================================================
# Tester systematiquement un agent avec des cas de test JSON :
#
# Terminal :
#   adk eval my_agent my_agent/eval_set.evalset.json
#
# Format du fichier eval_set.evalset.json :
# [
#   {
#     "name": "test_greeting",
#     "data": [
#       {"query": "Hello", "expected_response": "contains:Hi"},
#       {"query": "What can you do?", "expected_response": "contains:help"}
#     ]
#   }
# ]


# ============================================================
# 4. Plugins de securite (concepts)
# ============================================================
# ADK fournit des plugins pre-construits plus robustes que les callbacks :
#
# - Gemini-as-Judge : utilise Gemini Flash Lite pour detecter
#   prompt injection, jailbreak, contenu inapproprie
#
# - PII Redaction : masque automatiquement les donnees personnelles
#   (emails, numeros de telephone, SSN) avant traitement
#
# - Model Armor : interroge l'API Model Armor pour verifier
#   la securite du contenu a chaque etape
#
# Les plugins s'appliquent a TOUS les agents (transversaux)
# contrairement aux callbacks qui sont par-agent.


# ============================================================
# 5. MCP Tools (Model Context Protocol)
# ============================================================
# Standard ouvert pour integrer des services externes.
# Permet de connecter n'importe quel serveur MCP comme tool :
#
# from google.adk.tools.mcp_tool import MCPTool
#
# mcp_tool = MCPTool(
#     server_url="http://localhost:3000",
#     tool_name="web_search",
# )


# ============================================================
# 6. OpenAPI Tools
# ============================================================
# Integrer une API REST via sa spec OpenAPI :
#
# from google.adk.tools.openapi_tool import OpenAPITool
#
# api_tool = OpenAPITool.from_spec(
#     spec_url="https://petstore.swagger.io/v2/swagger.json",
#     operation_id="getPetById",
# )


# ============================================================
# 7. Streaming (reponses en temps reel)
# ============================================================
# Pour l'UX en production : les reponses arrivent token par token.
# Terminal : adk run --streaming my_agent
# API :     POST /run_sse avec "streaming": true


# ============================================================
# 8. A2A Protocol (Agent-to-Agent)
# ============================================================
# Protocol pour communication entre agents de systemes differents.
# Un agent ADK peut exposer ses capacites via A2A et etre appele
# par des agents d'autres frameworks.
# Terminal : adk deploy cloud_run --a2a


# ============================================================
# Agent executable pour ce step
# ============================================================

def save_code(code: str) -> dict:
    """Saves code and returns metrics.

    Args:
        code: The source code to save.

    Returns:
        Dictionary with save confirmation.
    """
    return {"status": "success", "line_count": len(code.strip().splitlines())}


root_agent = Agent(
    name="advanced_demo",
    model="gemini-2.5-flash",
    description="Demo of advanced ADK concepts.",
    instruction=(
        "You are an advanced demo agent.\n"
        "You can write code (save with save_code) and request approvals (request_approval).\n"
        "When the user asks to buy something, use request_approval.\n"
        "When asked to write code, write it and use save_code."
    ),
    tools=[save_code, approval_tool],
)
