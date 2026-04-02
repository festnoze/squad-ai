"""Corrige exercice 6 - ParallelAgent traduction parallele."""

from google.adk.agents import Agent, ParallelAgent, SequentialAgent


def analyze_text(text: str) -> dict:
    """Analyzes the source text before translation.

    Args:
        text: The text to analyze.

    Returns:
        Dictionary with text analysis.
    """
    words = text.split()
    return {
        "status": "success",
        "word_count": len(words),
        "char_count": len(text),
        "detected_language": "English",
    }


def translate_french(text: str) -> dict:
    """Translates text to French.

    Args:
        text: The text to translate.

    Returns:
        Dictionary with the French translation.
    """
    return {"status": "success", "translation": f"[FR] {text}", "language": "French"}


def translate_spanish(text: str) -> dict:
    """Translates text to Spanish.

    Args:
        text: The text to translate.

    Returns:
        Dictionary with the Spanish translation.
    """
    return {"status": "success", "translation": f"[ES] {text}", "language": "Spanish"}


def translate_japanese(text: str) -> dict:
    """Translates text to Japanese.

    Args:
        text: The text to translate.

    Returns:
        Dictionary with the Japanese translation.
    """
    return {"status": "success", "translation": f"[JP] {text}", "language": "Japanese"}


text_analyzer = Agent(
    name="text_analyzer",
    model="gemini-2.5-flash",
    description="Analyzes source text before translation.",
    instruction="Analyze the user's text using analyze_text. Present the analysis.",
    tools=[analyze_text],
    output_key="analysis",
)

french_translator = Agent(
    name="french_translator",
    model="gemini-2.5-flash",
    description="Translates to French.",
    instruction="Translate the text from the analysis to French using translate_french.\n\nAnalysis: {analysis}",
    tools=[translate_french],
    output_key="french_translation",
)

spanish_translator = Agent(
    name="spanish_translator",
    model="gemini-2.5-flash",
    description="Translates to Spanish.",
    instruction="Translate the text from the analysis to Spanish using translate_spanish.\n\nAnalysis: {analysis}",
    tools=[translate_spanish],
    output_key="spanish_translation",
)

japanese_translator = Agent(
    name="japanese_translator",
    model="gemini-2.5-flash",
    description="Translates to Japanese.",
    instruction="Translate the text from the analysis to Japanese using translate_japanese.\n\nAnalysis: {analysis}",
    tools=[translate_japanese],
    output_key="japanese_translation",
)

parallel_translators = ParallelAgent(
    name="parallel_translators",
    description="Translates to 3 languages in parallel.",
    sub_agents=[french_translator, spanish_translator, japanese_translator],
)

merger = Agent(
    name="merger",
    model="gemini-2.5-flash",
    description="Merges all translations into a final report.",
    instruction=(
        "Compile all translations into a formatted report:\n\n"
        "French: {french_translation}\n"
        "Spanish: {spanish_translation}\n"
        "Japanese: {japanese_translation}\n\n"
        "Present them clearly."
    ),
    output_key="final_translations",
)

root_agent = SequentialAgent(
    name="translation_pipeline",
    description="Analyze -> parallel translate (FR/ES/JP) -> merge.",
    sub_agents=[text_analyzer, parallel_translators, merger],
)
