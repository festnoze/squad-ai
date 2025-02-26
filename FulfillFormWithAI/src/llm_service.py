
from typing import List
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.helpers.file_helper import file
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.llm_helper import Llm
from common_tools.models.llm_info import LlmInfo
from common_tools.helpers.env_helper import EnvHelper
from common_tools.langchains.langchain_factory import LangChainFactory
from models.field import Field
from models.form import Form
#
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough

from models.group import Group
from models.str_list_pydantic import StringsListPydantic

class LlmService:
    def __init__(self, llms_infos: list[LlmInfo] = None):
        if llms_infos is None:
            llms_infos = EnvHelper.get_llms_infos_from_env_config(skip_commented_lines=True)

        self.llms_infos = llms_infos
        self.llms = LangChainFactory.create_llms_from_infos(llms_infos)
        self.llm = self.llms[0]

    async def query_user_to_fill_form_async(self, form: Form):
        while not form.validate().is_valid:
            for group in form.groups:
                while not group.validate().is_valid:                    
                    # Ask user for the whole group values
                    await self.query_user_to_fill_group_fields_async(group)                    
                    invalid_fields = [field for field in group.fields if not field.is_validated]
                    
                    if any(invalid_fields) and len(invalid_fields) != len(group.fields):
                        # Re-ask user for fields with invalid value only
                        for invalid_field in invalid_fields:
                            while not invalid_field.validate().is_valid:
                                await self.query_user_to_fill_field_value_async(invalid_field)
        return form

    async def query_user_to_fill_group_fields_async(self, group):
        group_question = await self.get_question_for_group_values_async(group)
        print("\nQuestion groupée :")
        print(group_question)
        answer_text = input()
        fields_values = await self.get_group_values_from_text_async(group, answer_text)
        if fields_values and isinstance(fields_values, dict):
            inner_key = next(iter(fields_values))
            if isinstance(fields_values[inner_key], list) and any(fields_values[inner_key]):
                fields_values = fields_values[inner_key]        
        group.set_values(fields_values)
    
    async def get_question_for_group_values_async(self, group: Group):
        query_group_prompt = file.get_as_str("src/prompts/group_query_for_values_prompt.txt")
        fields_infos = []
        for field in group.fields:
            fields_infos.append(f"{field.name}: {field.description}")

        fields_infos_str = "- " + "\n- ".join(fields_infos)
        query_group_prompt = query_group_prompt.replace("{group_name}", group.name)
        query_group_prompt = query_group_prompt.replace("{group_desc}", group.description)
        query_group_prompt = query_group_prompt.replace("{fields_infos}", fields_infos_str)
        promptlate = ChatPromptTemplate.from_template(query_group_prompt)
        chain = promptlate | self.llm | RunnablePassthrough()
        question = await Llm.invoke_chain_with_input_async("query form group", chain)
        return Llm.get_content(question)
    
    async def query_user_to_fill_field_value_async(self, field: Field):
        if field.is_validated:
            return
        print("\nQuestion simple :")
        field_question = await self.get_question_to_fix_field_value_async(field)
        print(field_question)
        answer = input()
        field.value = answer

    async def get_question_to_fix_field_value_async(self, field: Field):
        query_field_prompt = file.get_as_str("src/prompts/query_fixing_single_field_prompt.txt")
        query_field_prompt = query_field_prompt.replace("{field_name}", field.name)
        query_field_prompt = query_field_prompt.replace("{field_desc}", field.description)
        query_field_prompt = query_field_prompt.replace("{field_previous_value}", field.value if field.value else "null")
        field_validation = field.validate()
        if field_validation.is_valid:
            raise ValueError("Field is validated and cannot be fixed")
        query_field_prompt = query_field_prompt.replace("{field_previous_value_error_message}", field_validation.errors[0].message if field_validation.errors and any(field_validation.errors) else "<no error message>")
        query_field_prompt = query_field_prompt.replace("{field_infos}", str(field))

        promptlate = ChatPromptTemplate.from_template(query_field_prompt)
        chain = promptlate | self.llm | RunnablePassthrough()
        response = await Llm.invoke_chain_with_input_async("query form field", chain)
        return Llm.get_content(response)
    
    async def get_group_values_from_text_async(self, group: Group, text: str):
        group_get_values_prompt = file.get_as_str("src/prompts/group_get_values_from_text_answer_prompt.txt")
        fields_infos = []
        for field in group.fields:
            fields_infos.append(f"{field.name}: {field.description}")

        fields_infos_str = "- " + "\n- ".join(fields_infos)
        group_get_values_prompt = group_get_values_prompt.replace("{group_name}", group.name)
        group_get_values_prompt = group_get_values_prompt.replace("{group_desc}", group.description)
        group_get_values_prompt = group_get_values_prompt.replace("{fields_infos}", fields_infos_str)
        group_get_values_prompt = group_get_values_prompt.replace("{text_answer}", text)
        promptlate = ChatPromptTemplate.from_template(group_get_values_prompt)
        chain = promptlate | self.llm | RunnablePassthrough()
        response = await Llm.invoke_chain_with_input_async("get json group values from user answer", chain)
        values_list = Llm.extract_json_from_llm_response(response)
        
        # In case of failure, fallback with output parser
        if values_list is None:
            prompt_for_output_parser, output_parser = Llm.get_prompt_and_json_output_parser(
                group_get_values_prompt,
                StringsListPydantic,
                List[str])
            values_list = await Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks_async("get output parsed group values from user answer", self.llms, output_parser, 5, prompt_for_output_parser)
        
        return values_list
