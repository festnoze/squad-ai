"""Exercice 9 - Recipe Forge : Pipeline complet.

Mission : Combiner TOUS les concepts en un pipeline de creation de recettes.
Architecture :
  recipe_forge (SequentialAgent)
    +-- creation_loop (LoopAgent, max=3)
    |     +-- recipe_writer
    |     +-- review_cycle (SequentialAgent)
    |           +-- parallel_critics (ParallelAgent)
    |           |     +-- nutrition_critic
    |           |     +-- taste_critic
    |           |     +-- difficulty_critic
    |           +-- judge (escalate si ok)
    +-- presentation (rapport final)
"""

from typing import Optional

from google.adk.agents import Agent, LoopAgent, ParallelAgent, SequentialAgent
from google.adk.agents.context import Context
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types


# ============================================================
# TODO 1: CALLBACKS
# ============================================================

# allergen_guardrail(context, llm_request) -> Optional[LlmResponse]
#   - Bloquer si le message contient des allergenes dangereux (ex: "peanut allergy")
#   - Retourner LlmResponse avec un message d'avertissement
#   - Sinon return None

# validate_ingredients(tool, args, context) -> Optional[dict]
#   - Si tool.name == "write_recipe" et args["dish"] est trop court (< 3 chars)
#   - Retourner {"status": "error", "message": "Nom du plat trop court"}
#   - Sinon return None


# ============================================================
# TODO 2: TOOLS
# ============================================================

# write_recipe(dish: str, tool_context: ToolContext) -> dict
#   - Genere une recette mock (ingredients + etapes)
#   - Stocke dans tool_context.state["current_recipe"]
#   - Lit tool_context.state.get("judge_feedback") pour incorporer le feedback
#   - Retourne {"status": "success", "recipe": "..."}

# critique_nutrition(recipe: str) -> dict
#   - Critique les aspects nutritionnels (mock)

# critique_taste(recipe: str) -> dict
#   - Critique le gout et l'equilibre des saveurs (mock)

# critique_difficulty(recipe: str) -> dict
#   - Critique la difficulte de realisation (mock)

# judge_recipe(review_summary: str, tool_context: ToolContext) -> dict
#   - Evalue le resume des critiques
#   - Si iteration >= 3 : tool_context.actions.escalate = True
#   - Retourne {"status": "approved"} ou {"status": "needs_work"}


# ============================================================
# TODO 3: AGENTS - Construis l'architecture piece par piece
# ============================================================

# recipe_writer = Agent(
#     name="recipe_writer", model="gemini-2.5-flash",
#     instruction="...", tools=[write_recipe],
#     output_key="current_recipe",
#     before_model_callback=allergen_guardrail,
#     before_tool_callback=validate_ingredients,
# )

# nutrition_critic = Agent(..., output_key="nutrition_review")
# taste_critic = Agent(..., output_key="taste_review")
# difficulty_critic = Agent(..., output_key="difficulty_review")

# parallel_critics = ParallelAgent(
#     name="parallel_critics",
#     sub_agents=[nutrition_critic, taste_critic, difficulty_critic],
# )

# judge = Agent(
#     ..., tools=[judge_recipe], output_key="judge_feedback"
#     instruction lit {nutrition_review}, {taste_review}, {difficulty_review}
# )

# review_cycle = SequentialAgent(
#     name="review_cycle",
#     sub_agents=[parallel_critics, judge],
# )

# creation_loop = LoopAgent(
#     name="creation_loop",
#     sub_agents=[recipe_writer, review_cycle],
#     max_iterations=3,
# )

# presentation = Agent(
#     ..., instruction lit {current_recipe} et {judge_feedback},
#     output_key="final_output"
# )


# ============================================================
# TODO 4: ASSEMBLAGE FINAL
# ============================================================

# root_agent = SequentialAgent(
#     name="recipe_forge",
#     sub_agents=[creation_loop, presentation],
# )

root_agent = None  # TODO: remplace par SequentialAgent(...)
