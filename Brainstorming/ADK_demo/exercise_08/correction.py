"""Corrige exercice 7 - LoopAgent jeu de devinettes."""

from google.adk.agents import Agent, LoopAgent
from google.adk.tools.tool_context import ToolContext

RIDDLE = "I have cities but no houses, forests but no trees, and water but no fish. What am I?"
ANSWER = "map"
HINTS = [
    "Think about something you can look at but not live in.",
    "It represents the world but isn't the world itself.",
    "You might find one in a glove compartment.",
]


def ask_riddle(tool_context: ToolContext) -> dict:
    """Poses a riddle and gives a progressive hint each iteration.

    Returns:
        Dictionary with the riddle and current hint.
    """
    iteration = tool_context.state.get("riddle_iteration", 0)
    tool_context.state["answer"] = ANSWER
    hint = HINTS[min(iteration, len(HINTS) - 1)]
    tool_context.state["hint"] = hint
    tool_context.state["riddle_iteration"] = iteration + 1
    return {
        "status": "success",
        "riddle": RIDDLE,
        "hint": hint,
        "attempt": iteration + 1,
    }


def check_guess(guess: str, tool_context: ToolContext) -> dict:
    """Checks if the guess matches the riddle answer.

    Args:
        guess: The guessed answer.

    Returns:
        Dictionary with result (correct or wrong).
    """
    answer = tool_context.state.get("answer", "")
    if guess.strip().lower() == answer.lower():
        tool_context.actions.escalate = True
        return {"status": "correct", "message": f"Yes! The answer is '{answer}'."}
    return {"status": "wrong", "message": f"'{guess}' is not correct. Try again!"}


riddle_master = Agent(
    name="riddle_master",
    model="gemini-2.5-flash",
    description="Poses riddles with progressive hints.",
    instruction=(
        "Use ask_riddle to pose the riddle. "
        "Present the riddle and the current hint clearly."
    ),
    tools=[ask_riddle],
    output_key="current_riddle",
)

guesser = Agent(
    name="guesser",
    model="gemini-2.5-flash",
    description="Attempts to guess the riddle answer.",
    instruction=(
        "Try to guess the answer to this riddle:\n{current_riddle}\n\n"
        "Current hint: {hint}\n\n"
        "Use check_guess with your best guess."
    ),
    tools=[check_guess],
    output_key="guess_result",
)

root_agent = LoopAgent(
    name="riddle_game",
    description="Riddle game loop: pose riddle -> guess -> repeat until correct.",
    sub_agents=[riddle_master, guesser],
    max_iterations=5,
)
