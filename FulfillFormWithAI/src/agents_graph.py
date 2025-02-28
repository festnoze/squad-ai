from langchain_core.language_models import BaseChatModel
from langgraph.graph import StateGraph, END
from common_tools.models.langgraph_agent_state import AgentState

from agent_tools import extract_values_from_conversation, fill_form, interpret_user_response, validate_form
from agents import AgentHIL, AgentSuperviseur

class LangGraphFormSupervisor:
    def __init__(self, llm: BaseChatModel) -> None:
        self.llm = llm

    def build_graph(self):
        """Construit et compile le graphe LangGraph."""
        workflow = StateGraph(AgentState)

        workflow.add_node("superviseur", AgentSuperviseur().decide_next_step)
        workflow.add_node("extraction", extract_values_from_conversation)
        workflow.add_node("hil", AgentHIL().ask_user)
        workflow.add_node("interpretation", interpret_user_response)
        workflow.add_node("fill_form", fill_form)
        workflow.add_node("validation", validate_form)

        workflow.set_entry_point("superviseur")

        workflow.add_conditional_edges("superviseur", AgentSuperviseur().decide_next_step, {
            "hil": "hil",
            "end": END
        })

        workflow.add_edge("hil", "interpretation")
        workflow.add_edge("interpretation", "fill_form")
        workflow.add_edge("fill_form", "validation")
        workflow.add_edge("validation", "superviseur")

        return workflow.compile()


# ================== Exécution du Workflow ==================

if __name__ == "__main__":
    print("🔄 Construction du LangGraph pour le remplissage de formulaire...")
    supervisor = LangGraphFormSupervisor(None)
    workflow = supervisor.build_graph()
    print("✅ Graphe LangGraph compilé et prêt à l'exécution !")