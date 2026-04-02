"""Corrige exercice 4 - Delegation multi-agent."""

from google.adk.agents import Agent


def translate_to_french(text: str) -> dict:
    """Translates text to French and returns the result.

    Args:
        text: The text to translate to French.

    Returns:
        Dictionary with the translation.
    """
    return {"status": "success", "translation": f"[FR] {text}", "language": "French"}


def translate_to_spanish(text: str) -> dict:
    """Translates text to Spanish and returns the result.

    Args:
        text: The text to translate to Spanish.

    Returns:
        Dictionary with the translation.
    """
    return {"status": "success", "translation": f"[ES] {text}", "language": "Spanish"}


def translate_to_german(text: str) -> dict:
    """Translates text to German and returns the result.

    Args:
        text: The text to translate to German.

    Returns:
        Dictionary with the translation.
    """
    return {"status": "success", "translation": f"[DE] {text}", "language": "German"}


french_translator = Agent(
    name="french_translator",
    model="gemini-2.5-flash",
    description="Specialist in French translation. Delegate here when the user wants something translated to French.",
    instruction="You are a French translator. Use translate_to_french to translate the text.",
    tools=[translate_to_french],
)

spanish_translator = Agent(
    name="spanish_translator",
    model="gemini-2.5-flash",
    description="Specialist in Spanish translation. Delegate here when the user wants something translated to Spanish.",
    instruction="You are a Spanish translator. Use translate_to_spanish to translate the text.",
    tools=[translate_to_spanish],
)

german_translator = Agent(
    name="german_translator",
    model="gemini-2.5-flash",
    description="Specialist in German translation. Delegate here when the user wants something translated to German.",
    instruction="You are a German translator. Use translate_to_german to translate the text.",
    tools=[translate_to_german],
)

root_agent = Agent(
    name="translation_bureau",
    model="gemini-2.5-flash",
    description="Coordinates translation requests to specialized translators.",
    instruction=(
        "You run a translation bureau. Route requests to the right translator:\n"
        "- French -> french_translator\n"
        "- Spanish -> spanish_translator\n"
        "- German -> german_translator\n\n"
        "Always delegate. Never translate yourself."
    ),
    sub_agents=[french_translator, spanish_translator, german_translator],
)
