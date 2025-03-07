import json
from typing import Optional
#
from common_tools.helpers.file_helper import file
from common_tools.models.file_already_exists_policy import FileAlreadyExistsPolicy
#
from langchain.schema.messages import HumanMessage
from langchain_core.language_models import BaseChatModel
#
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
#
from models.form_agent_state import FormAgentState
from agents import AgentSupervisor, AgentHIL, AgentInterpretation
# ================== Définition du Graph de workflow d'agents ================== #

class GraphWorkflowForm:
    def __init__(self) -> None:
        self.supervisor = AgentSupervisor()
        self.HIL = AgentHIL()
        self.interpretation = AgentInterpretation()

    def build_graph(self):
        """Builds and compiles the LangGraph workflow."""
        workflow = StateGraph(FormAgentState)

        # Agents & Tools        
        workflow.add_node("supervisor", self.supervisor.analyse_missing_form_fields)
        workflow.add_node("hil", self.HIL.build_question_async)
        workflow.add_node("ask", self.HIL.ask_question)
        workflow.add_node("interpretation", self.interpretation.interpret_user_response_async)
        workflow.add_node("fill_form", self.interpretation.fill_form)

        # Workflow Edges
        workflow.set_entry_point("supervisor")
        workflow.add_conditional_edges("supervisor", self.supervisor.decide_next_step, 
        {
            "supervisor": "supervisor",
            "hil": "hil",
            "end": END
        })
        workflow.add_edge("hil", "ask")
        workflow.add_edge("ask", "interpretation")
        workflow.add_edge("interpretation", "fill_form")
        workflow.add_edge("fill_form", "supervisor")
        return workflow

    async def run_async(self, yaml_path: str, conversation: Optional[str] = None, auto_answer: bool = True) -> dict:
        """Runs the workflow with an optional conversation for pre-filling the form."""
        print("🔄 Construction du graphe LangGraph ...")
        
        workflow = self.build_graph()
        memory_saver = MemorySaver()
        compiled_workflow = workflow.compile(checkpointer=memory_saver)
        print("✅ Graphe LangGraph consruit !")

        if auto_answer:
            AgentHIL.static_answers = [
                "je m'appelle Etienne",
                "Monsieur",
                "Bouvier",
                "+33606060606",
                "erezr@efze.com",
                "622, avenue des roses 34000",
                "MONS",
                "domaine RH, bachelor conseiller en formation",
            ]            
            print(f"🤖 The questions will be automatically answered with the following static answers: \n{' / '.join(AgentHIL.static_answers)}.")
            input("\n>>> Pressez 'Entrée' pour commencer le remplissage automatique du formulaire <<<\n")

        print("🔄 Workflow en cours d'execution ...")
        form_agent_state = FormAgentState(chat_history= [HumanMessage(conversation)] if conversation else [], form_info_file_path= yaml_path, missing_fields= None)
        result = await compiled_workflow.ainvoke(form_agent_state, {"recursion_limit": 50})

        print("\n✅ Formulaire completé !")
        file.write_file(result["form"].to_dict(), "outputs/form_filled.json", FileAlreadyExistsPolicy.AutoRename)
        file.write_file(result["form"].to_flatten_fields(), "outputs/form_filled_flatten.json", FileAlreadyExistsPolicy.AutoRename)

        return result["form"].to_dict()