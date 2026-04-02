"""Exercice 4 - Delegation multi-agent.

Mission : Un bureau de traduction avec 3 traducteurs specialises
et un coordinateur qui route selon la langue demandee.
"""

from google.adk.agents import Agent


# TODO 1: Creer `translate_to_french(text: str) -> dict`
#   - Retourne un dict mock avec la "traduction"
#   - Ex: {"status": "success", "translation": "Bonjour le monde", "language": "French"}


# TODO 2: Creer `translate_to_spanish(text: str) -> dict`


# TODO 3: Creer `translate_to_german(text: str) -> dict`


# TODO 4: Creer les 3 sub-agents specialises
#   Chaque agent a :
#   - Un name unique
#   - Une description CLAIRE (c'est ce que le coordinateur lit pour router !)
#   - Une instruction specifique
#   - Son tool de traduction
#
# french_translator = Agent(...)
# spanish_translator = Agent(...)
# german_translator = Agent(...)


# TODO 5: Creer le root_agent coordinateur
#   - name="translation_bureau"
#   - PAS de tools (il delegue uniquement)
#   - sub_agents avec les 3 traducteurs
#   - instruction qui explique comment router

root_agent = None  # TODO: remplace par Agent(...)
