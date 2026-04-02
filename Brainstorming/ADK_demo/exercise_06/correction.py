"""Corrige exercice 5 - SequentialAgent pipeline."""

from google.adk.agents import Agent, SequentialAgent


def save_joke(joke: str, topic: str) -> dict:
    """Saves a joke and returns metrics.

    Args:
        joke: The joke text.
        topic: The topic of the joke.

    Returns:
        Dictionary with save confirmation.
    """
    return {"status": "success", "message": f"Joke about '{topic}' saved", "length": len(joke)}


def save_critique(rating: int, feedback: str) -> dict:
    """Saves a joke critique with rating and feedback.

    Args:
        rating: Rating from 1 to 10.
        feedback: Detailed feedback on the joke.

    Returns:
        Dictionary with the critique.
    """
    return {"status": "success", "rating": rating, "feedback": feedback}


joke_writer = Agent(
    name="joke_writer",
    model="gemini-2.5-flash",
    description="Writes jokes on a given topic.",
    instruction=(
        "Write a joke about the user's topic. "
        "Then use save_joke to save it."
    ),
    tools=[save_joke],
    output_key="raw_joke",
)

joke_critic = Agent(
    name="joke_critic",
    model="gemini-2.5-flash",
    description="Critiques jokes for quality.",
    instruction=(
        "Critique this joke:\n{raw_joke}\n\n"
        "Use save_critique with a rating (1-10) and constructive feedback."
    ),
    tools=[save_critique],
    output_key="critique",
)

joke_formatter = Agent(
    name="joke_formatter",
    model="gemini-2.5-flash",
    description="Formats the final version of a joke.",
    instruction=(
        "Based on the original joke and critique, present the best version.\n\n"
        "Original: {raw_joke}\n"
        "Critique: {critique}\n\n"
        "Format it nicely with setup and punchline clearly separated."
    ),
    output_key="final_joke",
)

root_agent = SequentialAgent(
    name="joke_pipeline",
    description="Pipeline: write joke -> critique -> format final version.",
    sub_agents=[joke_writer, joke_critic, joke_formatter],
)
