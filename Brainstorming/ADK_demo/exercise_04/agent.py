"""Exercice 3 - Session State et ToolContext.

Mission : Un agent "shopping_list" qui gere une liste de courses.
Les items persistent entre les tours grace au state.
"""

from google.adk.agents import Agent
from google.adk.tools.tool_context import ToolContext


# TODO 1: Creer `add_item(item: str, quantity: int, tool_context: ToolContext) -> dict`
#   - Lire la liste actuelle depuis tool_context.state.get("shopping_list", {})
#   - Ajouter/mettre a jour l'item avec sa quantite
#   - Sauvegarder la liste dans tool_context.state["shopping_list"]
#   - Mettre a jour tool_context.state["item_count"] avec le nombre d'items
#   - Retourner un dict de confirmation


# TODO 2: Creer `remove_item(item: str, tool_context: ToolContext) -> dict`
#   - Lire la liste depuis le state
#   - Supprimer l'item (gerer le cas ou il n'existe pas)
#   - Mettre a jour le state
#   - Retourner un dict de confirmation ou d'erreur


# TODO 3: Creer `show_list(tool_context: ToolContext) -> dict`
#   - Lire la liste depuis le state
#   - Retourner un dict avec la liste complete


# TODO 4: Creer le root_agent
#   - name="shopping_list"
#   - instruction avec {item_count} pour afficher le nombre d'items courant
#   - output_key="last_action"
#   - tools avec les 3 fonctions

root_agent = None  # TODO: remplace par Agent(...)
