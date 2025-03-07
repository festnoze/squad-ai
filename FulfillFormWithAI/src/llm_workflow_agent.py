from langchain.schema.messages import HumanMessage, AIMessage
from agent_tools import FormTools
from models.form_agent_state import FormAgentState

class LLMWorkflowAgent:    
    async def run_workflow(self, state: dict[str, any]) -> dict[str, any]:
        if "form" not in state or not state["form"]:
            state = self.load_form_tool(state)
        while True:
            missing_fields: list = self.get_missing_fields_tool(state)
            if not missing_fields:
                break
            state["missing_fields"] = missing_fields
            state = await self.generate_question_tool(state)
            state = self.ask_question_tool(state)
            state = await self.interpret_response_tool(state)
            state = self.fill_form_tool(state)
        return state

    def load_form_tool(self, state: dict[str, any]) -> dict[str, any]:
        state["form"] = FormTools.load_form_from_yaml(state["form_info_file_path"])
        if "chat_history" in state:
            extracted_values: any = FormTools.extract_values_from_conversation(state["chat_history"], state["form"])
            if extracted_values:
                state["form"] = FormTools.fill_form_func(state["form"], extracted_values)
        return state

    def get_missing_fields_tool(self, state: dict[str, any]) -> list:
        return FormTools.get_missing_groups_and_fields(state["form"])

    async def generate_question_tool(self, state: dict[str, any]) -> dict[str, any]:
        next_item: any = state["missing_fields"][0]
        form_item_to_query: any = FormTools.find_form_item(state["form"], next_item)
        question: str = ""
        if next_item["field"] is None:
            question = await FormTools.generate_question_for_group_async(form_item_to_query)
        else:
            question = await FormTools.generate_question_for_field_async(form_item_to_query)
        if "chat_history" not in state:
            state["chat_history"] = []
        state["chat_history"].append(AIMessage(question))
        return state

    def ask_question_tool(self, state: dict[str, any]) -> dict[str, any]:
        user_answer: str = "default answer"
        state["chat_history"].append(HumanMessage(user_answer))
        return state

    async def interpret_response_tool(self, state: dict[str, any]) -> dict[str, any]:
        next_item: any = state["missing_fields"][0]
        user_answer: str = state["chat_history"][-1].content
        targeted_form_item: any = FormTools.find_form_item(state["form"], next_item)
        interpreted_user_answer: any = await FormTools.interpret_user_response_async(targeted_form_item, user_answer)
        linked_fields_and_values: any = FormTools.link_values_with_fields(interpreted_user_answer, targeted_form_item)
        state["extracted_values"] = linked_fields_and_values
        return state

    def fill_form_tool(self, state: dict[str, any]) -> dict[str, any]:
        state["form"] = FormTools.fill_form_func(state["form"], state["extracted_values"])
        return state
