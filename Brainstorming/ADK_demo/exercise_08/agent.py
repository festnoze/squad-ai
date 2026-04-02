"""Exercice 7 - LoopAgent (Boucle iterative).

Mission : Un jeu de devinettes en boucle.
RiddleMaster pose une devinette, Guesser tente de deviner.
La boucle s'arrete quand la reponse est correcte ou apres 5 iterations.
"""

from google.adk.agents import Agent, LoopAgent
from google.adk.tools.tool_context import ToolContext


# TODO 1: Creer `ask_riddle(tool_context: ToolContext) -> dict`
#   - Stocker la reponse dans tool_context.state["answer"] (ex: "shadow")
#   - A chaque iteration, donner un indice de plus dans tool_context.state["hint"]
#   - Retourner un dict avec la devinette
#   - Ex iteration 1: {"riddle": "What has no weight but can be seen?", "hint": "Think about light"}
#   - Ex iteration 2: {"riddle": "Same question", "hint": "It follows you everywhere"}


# TODO 2: Creer `check_guess(guess: str, tool_context: ToolContext) -> dict`
#   - Lire la reponse correcte depuis tool_context.state.get("answer")
#   - Comparer (case insensitive)
#   - Si correct : tool_context.actions.escalate = True  et retourner succes
#   - Si incorrect : retourner un dict avec "status": "wrong"


# TODO 3: Creer riddle_master (Agent)
#   - Utilise ask_riddle comme tool
#   - output_key="current_riddle"
# riddle_master = Agent(...)


# TODO 4: Creer guesser (Agent)
#   - Lit {current_riddle} et {hint} dans son instruction
#   - Utilise check_guess comme tool
#   - output_key="guess_result"
# guesser = Agent(...)


# TODO 5: Creer le root_agent LoopAgent
#   - sub_agents=[riddle_master, guesser]
#   - max_iterations=5

root_agent = None  # TODO: remplace par LoopAgent(...)
