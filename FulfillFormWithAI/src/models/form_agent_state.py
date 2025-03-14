from typing import Optional, Union
from models.form import Form
#
from common_tools.models.langgraph_agent_state import AgentState
from langchain.schema.messages import HumanMessage

class FormAgentState(AgentState):
    # The path to the form file
    form_structure_file_path: str = ''
    # The form to be filled
    form: Form = None
    # The missing fields in the form
    missing_fields: list[dict[str, Union[str, None]]] = []
    # The extracted values to integrate into form (from previous conversation or user question's answer)
    extracted_values: dict[str, any] = {}

    @staticmethod
    def set_initial_values(initial_values: dict[str, any]):
        for key, value in initial_values.items():
            if not hasattr(FormAgentState, key) and not not hasattr(AgentState, key):
                raise Exception(f"'{FormAgentState.set_initial_values.__name__}' fails as: FormAgentState has no attribute named '{key}'")
            if key == 'chat_history' and isinstance(value, str):
                if value:
                    value = [HumanMessage(line) for line in value.splitlines()]
                else:
                    value = []
            setattr(FormAgentState, key, value)

    
    @classmethod
    def factory(cls, initial_values: dict[str, any]) -> "FormAgentState":
        # Create an instance with default values.
        instance: FormAgentState = cls(
            chat_history=FormAgentState.chat_history,            
            form_structure_file_path=FormAgentState.form_structure_file_path,
            form=FormAgentState.form,
            missing_fields=FormAgentState.missing_fields,
            extracted_values=FormAgentState.extracted_values
        )
        # Update the instance using the logic from your static method,
        # but set the keys on the instance rather than the class.
        for key, value in initial_values.items():
            if key == 'chat_history' and isinstance(value, str):
                value = [HumanMessage(line) for line in value.splitlines()]
            # Only update if the value is not None.
            if value is not None:
                instance[key] = value
        return instance

    def create(self, state: dict[str, any] = {}):
        super().__init__(state)
        self.chat_history = state.get('chat_history', FormAgentState.chat_history)
        #
        self.form_structure_file_path = state.get('form_structure_file_path', FormAgentState.form_structure_file_path)
        self.form = state.get('form', FormAgentState.form)
        self.missing_fields = state.get('missing_fields', FormAgentState.missing_fields)
        self.extracted_values = state.get('extracted_values', FormAgentState.extracted_values)

    # def create(self, chat_history: Optional[list[HumanMessage]] = None, form_structure_file_path: Optional[str] = None, **kwargs):
    #     init_kwargs = {}

    #     if chat_history is not None:
    #         init_kwargs["chat_history"] = chat_history

    #     if form_structure_file_path is not None:
    #         self.form_structure_file_path = form_structure_file_path

    #     init_kwargs.update(kwargs)
    #     super().__init__(**init_kwargs)