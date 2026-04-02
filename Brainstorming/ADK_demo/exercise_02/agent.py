"""Exercice 2 - Agent avec plusieurs outils.

Mission : Un agent "math_tutor" avec 3 outils mathematiques.
Le LLM doit choisir le bon outil selon la question de l'utilisateur.
"""

from google.adk.agents import Agent


# TODO 1: Creer `save_solution(equation: str, solution: str, steps: list[str]) -> dict`
#   - Docstring : sauvegarde la solution d'une equation
#   - Le LLM resout l'equation lui-meme, ce tool enregistre le resultat
#   - Retourne un dict avec "status" et "message"


# TODO 2: Creer `save_explanation(concept: str, explanation: str) -> dict`
#   - Docstring : sauvegarde l'explication d'un concept
#   - Le LLM explique lui-meme, ce tool enregistre


# TODO 3: Creer `generate_quiz(difficulty: str, question_count: int = 3) -> dict`
#   - Docstring : genere un quiz (ce tool-ci PEUT retourner du contenu mock)
#   - difficulty: "easy", "medium" ou "hard"
#   - Retourne un dict avec des questions mock (c'est du contenu statique, c'est ok)
#   - Ex: {"status": "success", "questions": ["What is 2+2?", ...]}


# TODO 4: Creer le root_agent avec les 3 outils
#   - name="math_tutor"
#   - L'instruction doit expliquer quand utiliser chaque tool

root_agent = None  # TODO: remplace par Agent(...)
