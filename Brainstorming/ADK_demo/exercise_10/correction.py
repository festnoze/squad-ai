"""Corrige exercice 9 - Recipe Forge pipeline complet."""

from typing import Optional

from google.adk.agents import Agent, LoopAgent, ParallelAgent, SequentialAgent
from google.adk.agents.context import Context
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types


# --- Callbacks ---
def allergen_guardrail(context: Context, llm_request: LlmRequest) -> Optional[LlmResponse]:
    """Blocks requests mentioning dangerous allergens."""
    if llm_request.contents:
        last = llm_request.contents[-1]
        if last.role == "user" and last.parts:
            text = (last.parts[0].text or "").lower()
            for allergen in ["peanut allergy", "deadly allergy", "anaphylaxis"]:
                if allergen in text:
                    return LlmResponse(
                        content=types.Content(
                            role="model",
                            parts=[types.Part(text=f"ATTENTION: Allergen dangereux detecte ('{allergen}'). Consultez un medecin.")],
                        )
                    )
    return None


def validate_ingredients(tool: BaseTool, args: dict, context: Context) -> Optional[dict]:
    """Validates recipe tool arguments."""
    if tool.name == "write_recipe":
        dish = args.get("dish", "")
        if len(dish.strip()) < 3:
            return {"status": "error", "message": "Nom du plat trop court (min 3 caracteres)."}
    return None


# --- Tools ---
def write_recipe(dish: str, tool_context: ToolContext) -> dict:
    """Writes or refines a recipe, incorporating prior feedback.

    Args:
        dish: The name of the dish to create a recipe for.

    Returns:
        Dictionary with the recipe.
    """
    iteration = tool_context.state.get("iteration", 0) + 1
    tool_context.state["iteration"] = iteration
    feedback = tool_context.state.get("judge_feedback", "No prior feedback.")
    tool_context.state["current_recipe"] = f"Recipe for {dish} (v{iteration})"
    return {
        "status": "success",
        "dish": dish,
        "iteration": iteration,
        "incorporated_feedback": feedback,
    }


def critique_nutrition(recipe: str) -> dict:
    """Critiques the nutritional aspects of a recipe.

    Args:
        recipe: The recipe text to critique.

    Returns:
        Dictionary with nutritional critique.
    """
    return {"status": "success", "aspect": "nutrition", "feedback": "Good balance of macronutrients."}


def critique_taste(recipe: str) -> dict:
    """Critiques the taste and flavor balance of a recipe.

    Args:
        recipe: The recipe text to critique.

    Returns:
        Dictionary with taste critique.
    """
    return {"status": "success", "aspect": "taste", "feedback": "Well-balanced flavors."}


def critique_difficulty(recipe: str) -> dict:
    """Critiques the difficulty level of a recipe.

    Args:
        recipe: The recipe text to critique.

    Returns:
        Dictionary with difficulty critique.
    """
    return {"status": "success", "aspect": "difficulty", "feedback": "Accessible for intermediate cooks."}


def judge_recipe(overall_score: int, summary: str, tool_context: ToolContext) -> dict:
    """Judges the recipe based on all critiques and decides if it passes.

    Args:
        overall_score: Score from 1 to 10.
        summary: Summary of all critiques.

    Returns:
        Dictionary with approval status.
    """
    tool_context.state["judge_feedback"] = summary
    iteration = tool_context.state.get("iteration", 1)
    if overall_score >= 8 or iteration >= 3:
        tool_context.actions.escalate = True
        return {"status": "approved", "score": overall_score}
    return {"status": "needs_work", "score": overall_score}


# --- Agents ---
recipe_writer = Agent(
    name="recipe_writer",
    model="gemini-2.5-flash",
    description="Writes or refines a recipe.",
    instruction=(
        "Write a recipe for the user's request using write_recipe.\n"
        "Prior feedback: {judge_feedback}"
    ),
    tools=[write_recipe],
    output_key="current_recipe",
    before_model_callback=allergen_guardrail,
    before_tool_callback=validate_ingredients,
)

nutrition_critic = Agent(
    name="nutrition_critic",
    model="gemini-2.5-flash",
    description="Critiques recipe nutrition.",
    instruction="Critique the nutrition of: {current_recipe}\nUse critique_nutrition.",
    tools=[critique_nutrition],
    output_key="nutrition_review",
)

taste_critic = Agent(
    name="taste_critic",
    model="gemini-2.5-flash",
    description="Critiques recipe taste.",
    instruction="Critique the taste of: {current_recipe}\nUse critique_taste.",
    tools=[critique_taste],
    output_key="taste_review",
)

difficulty_critic = Agent(
    name="difficulty_critic",
    model="gemini-2.5-flash",
    description="Critiques recipe difficulty.",
    instruction="Critique the difficulty of: {current_recipe}\nUse critique_difficulty.",
    tools=[critique_difficulty],
    output_key="difficulty_review",
)

parallel_critics = ParallelAgent(
    name="parallel_critics",
    description="Runs nutrition, taste, and difficulty critiques in parallel.",
    sub_agents=[nutrition_critic, taste_critic, difficulty_critic],
)

judge = Agent(
    name="judge",
    model="gemini-2.5-flash",
    description="Combines critiques and decides pass/fail.",
    instruction=(
        "Combine these critiques:\n"
        "Nutrition: {nutrition_review}\nTaste: {taste_review}\nDifficulty: {difficulty_review}\n\n"
        "Give an overall score (1-10) and use judge_recipe."
    ),
    tools=[judge_recipe],
    output_key="judge_feedback",
)

review_cycle = SequentialAgent(
    name="review_cycle",
    description="Parallel critics then judge.",
    sub_agents=[parallel_critics, judge],
)

creation_loop = LoopAgent(
    name="creation_loop",
    description="Write recipe -> review -> refine until approved.",
    sub_agents=[recipe_writer, review_cycle],
    max_iterations=3,
)

presentation = Agent(
    name="presentation",
    model="gemini-2.5-flash",
    description="Presents the final recipe.",
    instruction=(
        "Present the final approved recipe:\n\n"
        "Recipe: {current_recipe}\n"
        "Review: {judge_feedback}\n\n"
        "Format it beautifully with ingredients and steps."
    ),
    output_key="final_output",
)

root_agent = SequentialAgent(
    name="recipe_forge",
    description="Complete recipe creation pipeline with review loop.",
    sub_agents=[creation_loop, presentation],
)
