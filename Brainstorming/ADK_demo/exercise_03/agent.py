"""Exercice 3 - Runtime, Configuration et Artifacts.

Mission : Un agent "note_taker" qui sauvegarde des notes comme artifacts.
"""

from google.adk.agents import Agent
from google.adk.tools.tool_context import ToolContext
from google.genai import types


# TODO 1: Definir une config LLM precise (temperature basse)
# PRECISE_CONFIG = types.GenerateContentConfig(temperature=..., max_output_tokens=...)


# TODO 2: Creer `async def asave_note(title: str, content: str, tool_context: ToolContext) -> dict`
#   - Creer un artifact avec types.Part.from_text(text=content)
#   - Sauvegarder avec await tool_context.save_artifact(filename=title, artifact=...)
#   - Retourner un dict de confirmation avec le numero de version


# TODO 3: Creer `async def aload_note(title: str, tool_context: ToolContext) -> dict`
#   - Charger avec await tool_context.load_artifact(filename=title)
#   - Gerer le cas ou l'artifact n'existe pas (retourne None)
#   - Retourner le contenu ou un message d'erreur


# TODO 4: Creer `async def alist_notes(tool_context: ToolContext) -> dict`
#   - Lister avec await tool_context.list_artifacts()
#   - Retourner la liste des noms de fichiers


# TODO 5: Creer le root_agent
#   - name="note_taker"
#   - generate_content_config=PRECISE_CONFIG
#   - tools=[asave_note, aload_note, alist_notes]

root_agent = None  # TODO: remplace par Agent(...)
