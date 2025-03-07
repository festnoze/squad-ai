from typing import Union
from models.form import Form
#
from common_tools.models.langgraph_agent_state import AgentState
from langchain.schema.messages import HumanMessage

class FormAgentState(AgentState):
    # The path to the form info file
    form_info_file_path: str = 'config/user_and_training_info_form.yaml'
    # The form to be filled
    form: Form = None
    # The missing fields in the form
    missing_fields: list[dict[str, Union[str, None]]] = [HumanMessage("Je m'appelle John Smith et je suis un développeur Python. J'habote à Paris, au 16, rue de la biche 75016 en Angleterre.")]
    # The extracted values to integrate into form (from previous conversation or user question's answer)
    extracted_values: dict[str, any] = {}