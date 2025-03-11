
# ================== Définition des Agents ================== #

from agent_tools import FormTools
from models.form import Form
from langchain.schema.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.types import interrupt, Command
from common_tools.helpers.file_helper import file

class AgentSupervisor:
    """Supervises the workflow, loads the YAML file, and orchestrates actions."""

    def __init__(self):
        self.initialized = False

    async def initialize_async(self, state):
        """Initialize the workflow: load form + fields values extraction from conversation."""        
        # Load form from yaml file
        print("🔄 Loading form from YAML...")
        state['form'] = file.get_as_yaml(state['form_info_file_path'])

        # Extract values from conversation if not already injected
        if 'chat_history' in state:
            print("🔍 Extracting values from conversation...\n")
            extracted_values = await FormTools.extract_values_from_conversation_async(state['chat_history'], Form.from_dict(state["form"]))
            if len(extracted_values) > 0:
                filled_form = FormTools.fill_form_with_provided_values(Form.from_dict(state["form"]), extracted_values)
                state["form"] = filled_form.to_dict()
        self.initialized = True
        return state

    def analyse_missing_form_fields(self, state):
        """Analyse form fields missing values."""
        if not self.initialized: 
            self.load_form_and_fill_from_conversation(state)
            return state
                
        # Identify missing groups or fields
        missing_fields = FormTools.get_missing_groups_and_fields(Form.from_dict(state["form"]))
        state['missing_fields'] = missing_fields
        return state

    def decide_next_step(self, state):
        """determines next action."""
        if not 'missing_fields' in state or state['missing_fields'] is None:
            return "analyse_missing_fields"
        if state["missing_fields"] and any(state["missing_fields"]):
            return "build_question"
        if state["missing_fields"] and not any(state["missing_fields"]) and self.is_form_validated(state):
            return "end"
        return "initialize"
        
    def is_form_validated(self, state: dict[str, any]) -> bool:
        """Validate the form."""
        is_valid = False
        if "form" in state:
            form = Form.from_dict(state["form"])
            is_valid = form.validate().is_valid
        return is_valid
    

class AgentHIL:    
    static_answers: list = [] 

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
        print(f"🤖 Question : {state["chat_history"][-1].content}")
        
        if not any(self.static_answers):
            user_answer: str = input("> ")
        else:
            user_answer = self.static_answers.pop(0)
        
        print(f"👤 Réponse : {user_answer}")

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
        filled_form = FormTools.fill_form_with_provided_values(Form.from_dict(state['form']), state['extracted_values'])
        state['form'] = filled_form.to_dict()
        return state

