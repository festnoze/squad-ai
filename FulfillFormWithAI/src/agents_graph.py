import json
from typing import Optional
from langchain_core.language_models import BaseChatModel
from langgraph.graph import StateGraph, END

from models.form_agent_state import FormAgentState

# from agent_tools import extract_values_from_conversation, fill_form, interpret_user_response, validate_form
# from agents import AgentHIL, AgentSuperviseur

# ================== Définition du Graph de workflow d'agents ================== #

class LangGraphFormSupervisor:
    def __init__(self, llm: BaseChatModel) -> None:
        self.llm = llm
        self.supervisor = AgentSuperviseur()
        self.HIL = AgentHIL()

    def build_graph(self):
        """Builds and compiles the LangGraph workflow."""
        workflow = StateGraph(FormAgentState)

        # Agents & Tools
        workflow.add_node("superviseur", self.supervisor.decide_next_step)
        workflow.add_node("hil", self.HIL.build_and_ask_question)
        workflow.add_node("interpretation", interpret_user_response)
        workflow.add_node("fill_form", fill_form)
        workflow.add_node("validation", validate_form)

        # Workflow Edges
        workflow.set_entry_point("superviseur")

        workflow.add_conditional_edges("superviseur", self.supervisor.decide_next_step, {
            "hil": "hil",
            "end": END
        })

        workflow.add_edge("hil", "interpretation")
        workflow.add_edge("interpretation", "fill_form")
        workflow.add_edge("fill_form", "validation")
        workflow.add_edge("validation", "superviseur")

        return workflow.compile()

    def run(self, conversation: Optional[str] = None):
        """Runs the workflow with an optional conversation for pre-filling the form."""
        initial_state = {"conversation": conversation}
        workflow = self.build_graph()
        print("🔄 Running the form completion workflow...")
        result = workflow.invoke(initial_state)

        print("\n✅ Form successfully completed!")
        print(json.dumps(result["form"].to_dict(), indent=2))


# ================== Définition des Outils ================== #

from langchain.tools import tool
from models.form import Form
from models.group import Group
from models.field import Field
from common_tools.helpers.file_helper import file
from common_tools.helpers.llm_helper import Llm
from common_tools.langchains.langchain_factory import LangChainFactory

def load_form_from_yaml(file_path: str) -> Form:
    """Load a form from a YAML file."""
    yaml_data = file.get_as_yaml(file_path)
    return create_form_from_yaml(yaml_data)

def create_form_from_yaml(yaml_data: dict[str, any]) -> Form:
    """Create a Form object from YAML data."""
    groups = [
        Group(
            name=group_data["name"],
            description=group_data["description"],
            fields=[
                Field(
                    name=field_data["name"],
                    description=field_data["description"],
                    type=field_data["type"],
                    optional=field_data.get("optional"),
                    default_value=field_data.get("default_value"),
                    allowed_values=field_data.get("allowed_values"),
                )
                for field_data in group_data["fields"]
            ],
        )
        for group_data in yaml_data["form"]["groups"]
    ]
    return Form(name=yaml_data["form"]["name"], groups=groups)

def extract_values_from_conversation(conversation: str, form: Form) -> dict[str, any]:
    """Analyze the conversation and extract values corresponding to form fields."""
    extracted_values = {}
    for group in form.groups:
        for field in group.fields:
            if field.name in conversation:
                extracted_values[field.name] = f"Extracted value for {field.name}"
    return extracted_values

@tool
def generate_question_for_group(group: Group) -> str:
    """Generate a question for filling a group of fields."""
    fields_infos = "\n".join([f"{field.name}: {field.description}" for field in group.fields])
    return f"Please provide values for the following fields in {group.name}: \n{fields_infos}"

@tool
def generate_question_for_field(field: Field) -> str:
    """Generate a question for an individual field."""
    return f"Please provide a value for {field.name}: {field.description}"

@tool
def interpret_user_response(user_response: str, group: Group) -> dict[str, any]:
    """Interpret user response to extract field values."""
    return {field.name: f"Extracted: {user_response}" for field in group.fields}

@tool
def fill_form(form: Form, extracted_values: dict[str, any]) -> Form:
    """Fill the form with extracted values."""
    return fill_form_func(form, extracted_values)

def fill_form_func(form: Form, extracted_values: dict[str, any]) -> Form:
    for group in form.groups:
        for field in group.fields:
            if f'{group.name}.{field.name}' in extracted_values:
                field.value = extracted_values.get(f'{group.name}.{field.name}')
    return form

@tool
def validate_form(form: Form) -> str:
    """Validate the form and return 'ok' or 'error'."""
    return "ok" if form.validate().is_valid else "error"

# ================== Définition des Agents ================== #

from typing import Optional
from langgraph.graph import StateGraph, END

#from agent_tools import extract_values_from_conversation, fill_form_func, generate_question_for_field, generate_question_for_group, load_form_from_yaml
from models.form import Form

class AgentSuperviseur:
    """Supervises the workflow, loads the YAML file, and orchestrates actions."""

    def __init__(self):
        self.initialized = False

    def decide_next_step(self, state):
        """Handles form loading, conversation extraction, and determines next action."""
        if not self.initialized: 
            self.initialize(state)
            return state
                
        # Identify missing groups or fields
        state['missing_fields'] = self.get_missing_groups_and_fields(self.form)

        missing_fields = { "missing_fields": self.get_missing_groups_and_fields(state["form"]) }
        return missing_fields if missing_fields["missing_fields"] else END
        
    def initialize(self, state):
        # Load the form from yaml file
        print("🔄 Loading form from YAML...")
        self.form = load_form_from_yaml(state['form_info_file_path'])
        state['form'] = self.form

        # Extract values from conversation if not already injected
        if not self.initialized:
            if 'chat_history' in state:
                print("🔍 Extracting values from conversation...")
                extracted_values = extract_values_from_conversation(state['chat_history'], self.form)
                self.form = fill_form_func(self.form, extracted_values)
            self.initialized = True
    
    def get_missing_groups_and_fields(self, form: any) -> list[dict[str, any]]:
        missing_groups_and_fields: list[dict[str, any]] = []
        for group in form.groups:
            if all(not field.is_validated for field in group.fields):
                missing_groups_and_fields.append({'group': group.name, 'field': None, 'value': None})
            else:
                for field in group.fields:
                    if not field.is_validated:
                        missing_groups_and_fields.append({'group': group.name, 'field': field.name, 'value': field.value if field.value else None})
        return missing_groups_and_fields


class AgentHIL:
    """Handles asking answers to the user (Human In the Loop)."""
    def build_and_ask_question(self, state: dict[str, any]) -> dict[str, any]:
        if len(state["missing_fields"]) > 1:
            group_name: str = state["missing_fields"][0]["group"]
            question: str = ""
            for group in state["form"].groups:
                if group.name == group_name:
                    question = generate_question_for_group(group)
                    break
        else:
            missing: dict[str, any] = state["missing_fields"][0]
            question: str = ""
            if missing["field"] is None:
                group_name: str = missing["group"]
                for group in state["form"].groups:
                    if group.name == group_name:
                        question = generate_question_for_group(group)
                        break
            else:
                for group in state["form"].groups:
                    if group.name == missing["group"]:
                        for field in group.fields:
                            if field.name == missing["field"]:
                                question = generate_question_for_field(field)
                                break
                        if question:
                            break
        print(f"🤖 {question}")
        user_answer: str = input("> ")
        return {"reponse_utilisateur": user_answer}