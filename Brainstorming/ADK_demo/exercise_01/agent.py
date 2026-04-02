"""Exercice 1 - Creer un agent basique avec un outil custom.

Mission : Un agent "poem_writer" qui genere des haikus.
Complete les TODO ci-dessous, puis teste avec `adk web` -> exercise_01.
"""

from google.adk.agents import Agent


# TODO 1: Creer une fonction `save_haiku` qui :
#   - Prend un parametre `haiku` (str) - le haiku ecrit par le LLM
#   - Prend un parametre optionnel `topic` (str) - le sujet du haiku
#   - Retourne un dict avec "status", "message", et "line_count"
#   - A une docstring claire (le LLM la lit pour comprendre l'outil !)
#
# IMPORTANT : le tool ne GENERE PAS le haiku. C'est le LLM qui l'ecrit.
# Le tool sert a le SAUVEGARDER et retourner des metriques.
#
# Exemple :
# def save_haiku(haiku: str, topic: str = "unknown") -> dict:
#     """Saves a haiku and returns metrics..."""
#     lines = haiku.strip().splitlines()
#     return {"status": "success", "message": f"Haiku saved ({len(lines)} lines)", ...}


# TODO 2: Creer le root_agent :
#   - name="poem_writer"
#   - model="gemini-2.5-flash"
#   - description= (decris ce que fait l'agent)
#   - instruction= (dis au LLM : ecris un haiku, puis utilise save_haiku pour le sauvegarder)
#   - tools= [save_haiku]

root_agent = None  # TODO: remplace None par Agent(...)
