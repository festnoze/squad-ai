"""Exercice 6 - ParallelAgent (Execution concurrente).

Mission : Un systeme de traduction parallele.
Pipeline : Analyzer -> Parallel(FR + ES + JP) -> Merger
"""

from google.adk.agents import Agent, ParallelAgent, SequentialAgent


# TODO 1: Creer `analyze_text(text: str) -> dict`
#   - Analyse basique du texte (mock) : nombre de mots, langue detectee
#   - Ex: {"status": "success", "word_count": 9, "detected_language": "English"}


# TODO 2: Creer les tools de traduction (mock)
# def translate_french(text: str) -> dict:
# def translate_spanish(text: str) -> dict:
# def translate_japanese(text: str) -> dict:


# TODO 3: Creer le TextAnalyzer
# text_analyzer = Agent(
#     name="text_analyzer",
#     ...,
#     output_key="analysis",
# )


# TODO 4: Creer les 3 traducteurs
#   Chacun lit {analysis} dans son instruction
#   Chacun a son propre output_key
#
# french_translator = Agent(..., output_key="french_translation")
# spanish_translator = Agent(..., output_key="spanish_translation")
# japanese_translator = Agent(..., output_key="japanese_translation")


# TODO 5: Creer le ParallelAgent avec les 3 traducteurs
# parallel_translators = ParallelAgent(...)


# TODO 6: Creer le TranslationMerger
#   - Lit {french_translation}, {spanish_translation}, {japanese_translation}
#   - Compile un rapport final
# merger = Agent(..., output_key="final_translations")


# TODO 7: Assembler le SequentialAgent
#   text_analyzer -> parallel_translators -> merger

root_agent = None  # TODO: remplace par SequentialAgent(...)
