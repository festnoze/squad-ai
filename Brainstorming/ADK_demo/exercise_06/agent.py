"""Exercice 5 - SequentialAgent (Pipeline deterministe).

Mission : Un pipeline de creation de blagues en 3 etapes.
JokeWriter -> JokeCritic -> JokeFormatter
"""

from google.adk.agents import Agent, SequentialAgent


# TODO 1: Creer `write_joke(topic: str) -> dict`
#   - Genere une blague brute (mock)
#   - Ex: {"status": "success", "joke": "Why do programmers prefer dark mode? ..."}


# TODO 2: Creer `critique_joke(joke: str) -> dict`
#   - Critique la blague (mock)
#   - Ex: {"status": "success", "rating": 6, "feedback": "Good setup but weak punchline"}


# TODO 3: Creer les 3 agents du pipeline
#
# joke_writer = Agent(
#     name="joke_writer",
#     model="gemini-2.5-flash",
#     instruction="...",
#     tools=[write_joke],
#     output_key="raw_joke",        # <- ecrit dans state["raw_joke"]
# )
#
# joke_critic = Agent(
#     name="joke_critic",
#     model="gemini-2.5-flash",
#     instruction="Critique cette blague : {raw_joke}...",  # <- lit state["raw_joke"]
#     tools=[critique_joke],
#     output_key="critique",
# )
#
# joke_formatter = Agent(
#     name="joke_formatter",
#     model="gemini-2.5-flash",
#     instruction="Formate la blague finale. Blague: {raw_joke}. Critique: {critique}. ...",
#     output_key="final_joke",
#     # Pas de tool necessaire, le LLM formate directement
# )


# TODO 4: Creer le root_agent SequentialAgent
#   - sub_agents dans le bon ordre !
#   - Rappel : PAS de model= ni instruction= sur un SequentialAgent

root_agent = None  # TODO: remplace par SequentialAgent(...)
