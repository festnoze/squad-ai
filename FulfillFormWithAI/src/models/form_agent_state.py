from typing import Union
from models.form import Form
#
from common_tools.models.langgraph_agent_state import AgentState

class FormAgentState(AgentState):
    # The path to the form info file
    form_info_file_path: str
    # The form to be filled
    form: Form = None
    # The missing fields in the form
    missing_fields: list[dict[str, Union[str, None]]]
    # The extracted values to integrate into form (from previous conversation or user question's answer)
    extracted_values: dict[str, any] = {}