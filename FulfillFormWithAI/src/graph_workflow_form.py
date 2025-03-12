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
from models.form import Form
from models.form_agent_state import FormAgentState
from agents import AgentSupervisor, AgentHIL, AgentInterpretation
# ================== Définition du Graph de workflow d'agents ================== #

class GraphWorkflowForm:
    def __init__(self) -> None:
        # Init. Agents
        self.supervisor = AgentSupervisor()
        self.HIL = AgentHIL()
        self.interpretation = AgentInterpretation()

        # Init. Graph
        self.graph = StateGraph(FormAgentState)

        # Set Agents & Tools
        self.graph.add_node("initialize", self.supervisor.initialize)   
        self.graph.add_node("extract_values_from_conversation", self.supervisor.extract_values_from_conversation_async)     
        self.graph.add_node("analyse_missing_fields", self.supervisor.analyse_missing_form_fields)
        self.graph.add_node("build_question", self.HIL.build_question_async)
        self.graph.add_node("ask_question", self.HIL.ask_question)
        self.graph.add_node("answer_interpretation", self.interpretation.interpret_user_response_async)
        self.graph.add_node("fill_form", self.interpretation.fill_form)

        # Set conditionnal and static edges
        self.graph.set_entry_point("initialize")
        self.graph.add_edge("initialize", "extract_values_from_conversation")
        self.graph.add_edge("extract_values_from_conversation", "analyse_missing_fields")
        self.graph.add_conditional_edges("analyse_missing_fields", self.supervisor.decide_next_step, 
        {
            "build_question": "build_question",
            "end": END
        })
        self.graph.add_edge("build_question", "ask_question")
        self.graph.add_edge("ask_question", "answer_interpretation")
        self.graph.add_edge("answer_interpretation", "fill_form")
        self.graph.add_edge("fill_form", "analyse_missing_fields")

        print("🔄 Construction du graphe LangGraph ...")        
        memory_saver = MemorySaver()
        self.compiled_graph = self.graph.compile(checkpointer=memory_saver)
        print("✅ Graphe LangGraph consruit !")

    async def run_async(self, yaml_path: str, conversation: Optional[str] = None) -> dict:
        """Runs the workflow with an optional conversation for pre-filling the form."""
        print("🔄 Workflow en cours d'execution ...")
        form_agent_state = FormAgentState(chat_history= [HumanMessage(conversation)] if conversation else [], form_info_file_path= yaml_path, missing_fields= None)
        result = await self.compiled_graph.ainvoke(form_agent_state, {"recursion_limit": 50, "configurable": {"thread_id": "thread-1"}})

        print("\n✅ Formulaire completé !")
        file.write_file(result["form"], "outputs/filled_form.json", FileAlreadyExistsPolicy.AutoRename)
        file.write_file(Form.from_dict(result["form"]).get_all_fields_values(), "outputs/filled_form_flatten_fields_values.json", FileAlreadyExistsPolicy.AutoRename)
        return result["form"]