"""Corrige exercice 1 - Agent basique avec un outil custom."""

from google.adk.agents import Agent


def save_haiku(haiku: str, topic: str = "unknown") -> dict:
    """Saves a haiku poem and returns metrics.

    Use this tool after writing a haiku to save it and get syllable analysis.

    Args:
        haiku: The haiku text to save (3 lines).
        topic: The topic of the haiku.

    Returns:
        Dictionary with save confirmation and haiku metrics.
    """
    lines = haiku.strip().splitlines()
    return {
        "status": "success",
        "message": f"Haiku about '{topic}' saved ({len(lines)} lines)",
        "line_count": len(lines),
    }


root_agent = Agent(
    name="poem_writer",
    model="gemini-2.5-flash",
    description="A poet agent that writes haikus on any topic.",
    instruction=(
        "You are a haiku poet. When the user gives you a topic:\n"
        "1. Write a haiku (3 lines: 5-7-5 syllables)\n"
        "2. Use the save_haiku tool to save it with the topic\n"
        "3. Present the haiku to the user"
    ),
    tools=[save_haiku],
)
