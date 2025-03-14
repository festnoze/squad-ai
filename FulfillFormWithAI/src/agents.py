from langchain.schema.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.types import interrupt, Command
#
from common_tools.helpers.file_helper import file
from common_tools.helpers.txt_helper import txt
#
from agent_tools import FormTools
from helper import Helper
from models.form import Form

# ================== Définition des Agents ================== #

class AgentSupervisor:
    """Supervises the workflow, loads the YAML file, and orchestrates actions."""

    def initialize(self, state: dict[str, any]):
        """Initialize the workflow: load form + fields values extraction from conversation."""        
        # Load form from yaml file
        txt.print("🔄 Loading form from YAML...")
        form_dict = file.get_as_yaml(state['form_structure_file_path'])
        state['form'] = Helper.resolve_file_references(form_dict, 'config/')
        txt.print("✅ Form loaded !")
        return state

    async def extract_values_from_conversation_async(self, state: dict[str, any]):
        """Extract values from conversation if exists."""
        if 'chat_history' in state:
            txt.print("🔍 Extracting values from conversation...\n")
            extracted_values = await FormTools.extract_values_from_conversation_async(state['chat_history'], Form.from_dict(state["form"]))
            txt.print("✅ Extracted values:")
            Helper.print_fields_values(extracted_values)
            state['extracted_values'] = extracted_values
        return state

    def analyse_missing_form_fields(self, state: dict[str, any]):
        """Analyse form's missing fields values."""
        missing_fields = FormTools.get_missing_groups_and_fields(Form.from_dict(state["form"]))
        state['missing_fields'] = missing_fields
        return state

    def decide_next_step(self, state: dict[str, any]):
        if any(state["missing_fields"]):
            return "build_question"
        if not any(state["missing_fields"]) and self.is_form_validated(state):
            return "end"
        raise interrupt("Error: No missing fields found, but form is not validated.")
        
    def is_form_validated(self, state: dict[str, any]) -> bool:
        """Validate the form."""
        return "form" in state and Form.from_dict(state["form"]).is_valid    

class AgentHIL:
    static_answers_file_path = 'inputs/form_automatic_answers.txt'    
    static_answers: list = []

    def __init__(self):
        if file.exists(AgentHIL.static_answers_file_path):
            AgentHIL.static_answers = file.get_as_str(AgentHIL.static_answers_file_path).splitlines()

    async def build_question_async(self, state: dict[str, any]):
        """Create a question to ask the user (Human In the Loop)."""
        if len(state["missing_fields"]) == 0:
            return
        next_item = state["missing_fields"][0]
        form_item_to_query = FormTools.get_group_or_field(Form.from_dict(state['form']), next_item)

        if next_item["field"] is None:
            question = await FormTools.generate_question_for_group_async(form_item_to_query)
        else:
            question = await FormTools.generate_question_for_field_async(form_item_to_query)
        
        state["chat_history"].append(AIMessage(question))
        return state
    
    def ask_question(self, state: dict[str, any]):
        """Ask the user to answer question (Human In the Loop)."""
        if not isinstance(state["chat_history"][-1], AIMessage):
            raise ValueError("Last message in chat history should be an AIMessage.")
        txt.print(f"🤖 Question : {state["chat_history"][-1].content}")
        
        if not any(self.static_answers):
            user_answer: str = input("> ")
        else:
            user_answer = self.static_answers.pop(0)
        
        txt.print(f"👤 Réponse : {user_answer}")
        state["chat_history"].append(HumanMessage(user_answer))
        return state
    
class AgentInterpretation:
    async def interpret_user_response_async(self, state: dict[str, any]) -> dict[str, any]:
        """Interpret user response to extract field values."""        
        if not isinstance(state["chat_history"][-1], HumanMessage):
            raise ValueError("Last message in chat history should be a HumanMessage.")
        if len(state["missing_fields"]) == 0:
            raise ValueError("No missing fields to interpret.")
           
        next_item = state["missing_fields"][0]
        user_answer = state["chat_history"][-1].content
        targeted_form_item = FormTools.get_group_or_field(Form.from_dict(state['form']), next_item)
        interpreted_user_answer = await FormTools.interpret_user_response_async(targeted_form_item, user_answer)
        linked_fields_and_values = FormTools.link_values_with_fields(interpreted_user_answer, targeted_form_item)
        state["extracted_values"] = linked_fields_and_values
        return state
    
    def fill_form(self, state: dict[str, any]) -> Form:
        """Fill the form with extracted values."""
        filled_form = FormTools.fill_form_with_provided_values(Form.from_dict(state['form']), state.get('extracted_values'))
        state['form'] = filled_form.to_dict()
        state['extracted_values'] = None
        return state

