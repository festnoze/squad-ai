from langgraph.graph import StateGraph, END

class AgentSuperviseur:
    def decide_next_step(self, state):
        """Détermine l'étape suivante en fonction de la validation."""
        if state.get("validation_result") == "erreur":
            return "hil"
        if state.get("champs_manquants"):
            return "hil"
        return END


class AgentHIL:
    def ask_user(self, state):
        """Pose une question à l'utilisateur et récupère la réponse."""
        print(state["question"])
        user_response = input("> ")
        return {"reponse_utilisateur": user_response}