from typing import Optional
#
from langchain.schema.messages import HumanMessage
from langchain_core.language_models import BaseChatModel
#
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
#
from common_tools.helpers.file_helper import file
from common_tools.models.file_already_exists_policy import FileAlreadyExistsPolicy
from common_tools.helpers.txt_helper import txt
#
from models.form import Form
from models.form_agent_state import FormAgentState
from agents import AgentSupervisor, AgentHIL, AgentInterpretation

# ================== Définition du Graph de workflow d'agents ================== #

class GraphWorkflowForm:
    def __init__(self, agent_state_initial_values: dict = {}) -> None:
        # Init. Agents
        self.supervisor = AgentSupervisor()
        self.HIL = AgentHIL()
        self.interpretation = AgentInterpretation()

        # Set default values for all Agent State
        FormAgentState.set_initial_values(agent_state_initial_values)

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
        self.graph.add_edge("extract_values_from_conversation", "fill_form")

        self.graph.add_conditional_edges("analyse_missing_fields", self.supervisor.decide_next_step, 
        {
            "build_question": "build_question",
            "end": END
        })
        self.graph.add_edge("build_question", "ask_question")
        self.graph.add_edge("ask_question", "answer_interpretation")
        self.graph.add_edge("answer_interpretation", "fill_form")
        self.graph.add_edge("fill_form", "analyse_missing_fields")

        txt.print("🔄 Construction du graphe LangGraph ...")        
        memory_saver = MemorySaver()
        self.compiled_graph = self.graph.compile(checkpointer=memory_saver)
        txt.print("✅ Graphe LangGraph consruit !")

    async def run_async(self, yaml_path: str = None, conversation: Optional[str] = None) -> dict:
        """Runs the workflow with an optional conversation for pre-filling the form."""
        txt.print("🔄 Workflow en cours d'execution ...")

        # Override the default values of Agent State
        form_agent_state = FormAgentState.factory({'form_structure_file_path': yaml_path, 'chat_history': conversation}) # Inherit from TypedDict, no class init. apply
        
        # Run the agentic workflow
        result = await self.compiled_graph.ainvoke(form_agent_state, {"recursion_limit": 50, "configurable": {"thread_id": "thread-1"}})

        txt.print("\n✅ Formulaire completé !")
        file.write_file(result["form"], "outputs/filled_form.json", FileAlreadyExistsPolicy.AutoRename)
        file.write_file(Form.from_dict(result["form"]).get_all_fields_values(), "outputs/filled_form_flatten_fields_values.json", FileAlreadyExistsPolicy.AutoRename)
        return result["form"]