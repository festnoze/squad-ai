"""Exercice 11 - Concepts avances.

Mission : Creer un agent "purchase_assistant" qui utilise LongRunningFunctionTool
pour demander une approbation avant tout achat.
"""

from google.adk.agents import Agent
from google.adk.tools import LongRunningFunctionTool


# TODO 1: Creer `request_purchase_approval(item: str, price: float, justification: str) -> dict`
#   - Retourne un dict avec "status": "pending" et les details
#   - C'est le LLM qui decide quand appeler ce tool


# TODO 2: Wrapper la fonction dans LongRunningFunctionTool
# purchase_tool = LongRunningFunctionTool(func=request_purchase_approval)


# TODO 3: Creer `save_purchase_record(item: str, price: float, approved: bool) -> dict`
#   - Un tool normal (pas long-running) pour enregistrer un achat
#   - Retourne confirmation


# TODO 4: Creer le root_agent
#   - name="purchase_assistant"
#   - tools=[purchase_tool, save_purchase_record]
#   - instruction : quand l'utilisateur veut acheter, demander approbation d'abord

root_agent = None  # TODO: remplace par Agent(...)
