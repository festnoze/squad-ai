import json
from typing import Optional
from langchain.schema.messages import HumanMessage
from langchain_core.language_models import BaseChatModel
from langgraph.graph import StateGraph, END
from models.form_agent_state import FormAgentState
from agents import AgentSupervisor, AgentHIL, AgentInterpretation
from common_tools.helpers.file_helper import file

# ================== Définition du Graph de workflow d'agents ================== #

class FormWorkflowGraph:
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
        return workflow.compile()

    async def run_async(self, yaml_path: str, conversation: Optional[str] = None) -> dict:
        """Runs the workflow with an optional conversation for pre-filling the form."""
        print("🔄 Construction du graphe LangGraph ...")
        workflow = self.build_graph()
        print("✅ Graphe LangGraph consruit !")
        
        print("🔄 Workflow en cours d'execution ...")
        form_agent_state = FormAgentState(chat_history= [HumanMessage(conversation)] if conversation else [], form_info_file_path= yaml_path, missing_fields= None)
        result = await workflow.ainvoke(form_agent_state, {"recursion_limit": 50})

        print("\n✅ Formulaire completé !")
        file.write_file(result["form"].to_dict(), "outputs/form_filled.json")
        file.write_file(result["form"].to_flatten_fields(), "outputs/form_filled_flatten.json")

        return result["form"].to_dict()