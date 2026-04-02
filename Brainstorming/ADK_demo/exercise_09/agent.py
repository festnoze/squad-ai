"""Exercice 8 - Callbacks (Guardrails et validation).

Mission : Ajouter 3 types de guardrails a un agent de chat :
  - Rate limiter (before_model)
  - Content filter (before_tool)
  - Response logger (after_model)
"""

from typing import Optional

from google.adk.agents import Agent
from google.adk.agents.context import Context
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.genai import types


# ============================================================
# TODO 1: Rate limiter (before_model_callback)
# ============================================================
# Signature : (context: Context, llm_request: LlmRequest) -> Optional[LlmResponse]
#
# - Lire le compteur depuis context.state.get("message_count", 0)
# - Incrementer et sauvegarder dans context.state["message_count"]
# - Si le compteur > 5 : retourner une LlmResponse bloquante
#   LlmResponse(content=types.Content(role="model",
#       parts=[types.Part(text="Rate limit atteint ! Max 5 messages.")]))
# - Sinon : return None (laisser passer)


# ============================================================
# TODO 2: Content filter (before_tool_callback)
# ============================================================
# Signature : (tool: BaseTool, args: dict, context: Context) -> Optional[dict]
#
# - Verifier si un des args contient un mot inapproprie
#   FORBIDDEN_WORDS = ["badword", "inappropriate", "offensive"]
# - Si oui : retourner un dict {"status": "blocked", "message": "Contenu inapproprie"}
# - Sinon : return None


# ============================================================
# TODO 3: Response logger (after_model_callback)
# ============================================================
# Signature : (context: Context, llm_response: LlmResponse) -> Optional[LlmResponse]
#
# - print() la reponse du LLM (llm_response.content.parts[0].text)
# - return None (on ne modifie pas la reponse, on la log juste)


# ============================================================
# Tool simple pour l'agent
# ============================================================
def echo_message(message: str) -> dict:
    """Repete le message de l'utilisateur avec un commentaire.

    Args:
        message: Le message a repeter.

    Returns:
        Dictionary with the echoed message.
    """
    return {"status": "success", "echo": message, "comment": "Message bien recu !"}


# ============================================================
# TODO 4: Creer le root_agent avec les 3 callbacks
# ============================================================
# root_agent = Agent(
#     name="guarded_chat",
#     model="gemini-2.5-flash",
#     instruction="...",
#     tools=[echo_message],
#     before_model_callback=...,
#     before_tool_callback=...,
#     after_model_callback=...,
# )

root_agent = None  # TODO: remplace par Agent(...)
