
import re
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.helpers.file_helper import file
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.llm_helper import Llm
from common_tools.models.llm_info import LlmInfo
from common_tools.helpers.env_helper import EnvHelper
from common_tools.langchains.langchain_factory import LangChainFactory
#
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain.schema.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.messages.base import BaseMessage
#
from models.form import Form
from models.group import Group
from models.field import Field
from models.generic_pydantic_structs import DictListPydantic, StringsListPydantic

class LlmService:
    def __init__(self, llms_infos: list[LlmInfo] = None):
        if llms_infos is None:
            llms_infos = EnvHelper.get_llms_infos_from_env_config(skip_commented_lines=True)

        self.llms_infos = llms_infos
        self.llms = LangChainFactory.create_llms_from_infos(llms_infos)
        self.llm = self.llms[0]

    async def query_user_to_fill_form_async(self, form: Form):
        while not form.validation_result.is_valid:
            for group in form.groups:
                while not group.perform_validation().is_valid:                    
                    # Ask user for the whole group values
                    await self.query_user_to_fill_group_fields_async(group)                    
                    invalid_fields = [field for field in group.fields if not field.is_valid]
                       
                    # Re-ask user for fields with invalid value only
                    if any(invalid_fields) and len(invalid_fields) != len(group.fields):
                        for invalid_field in invalid_fields:
                            while not invalid_field._perform_validation().is_valid:
                                await self.query_user_to_fill_field_value_async(invalid_field)
        return form

    async def query_user_to_fill_group_fields_async(self, group):
        group_question = await self.get_question_for_group_values_async(group)
        print("\nQuestion groupée :")
        print(group_question)
        answer_text = input('> ')
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

        lmessages = self.get_langchain_messages_from_html_tags_in_prompt(query_group_prompt, ['objectifs'])
        promptlate =  ChatPromptTemplate.from_messages(lmessages)
        # Or version w/o separating prompt's tags into separate messages
        # promptlate = ChatPromptTemplate.from_template(query_group_prompt)

        chain = promptlate | self.llm | RunnablePassthrough()
        question = await Llm.invoke_chain_with_input_async("query form group", chain)
        return Llm.get_content(question)
    
    async def query_user_to_fill_field_value_async(self, field: Field):
        if field.is_valid:
            return
        print("\nQuestion simple :")
        field_question = await self.get_question_to_fix_field_value_async(field)
        print(field_question)
        answer = input('> ')
        field.value = answer

    async def get_question_to_fix_field_value_async(self, field: Field):
        if field.is_valid:
            raise ValueError("Field value is already valid and don't need to be fixed")
        
        query_field_prompt = file.get_as_str("src/prompts/query_fixing_single_field_prompt.txt")
        query_field_prompt = query_field_prompt.replace("{field_name}", field.name)
        query_field_prompt = query_field_prompt.replace("{field_desc}", field.description)
        query_field_prompt = query_field_prompt.replace("{field_previous_value}", field.value if field.value else "null")
        query_field_prompt = query_field_prompt.replace("{field_previous_value_error_message}", field.validation_result.errors[0].message if any(field.validation_result.errors) else "<no error message>")
        query_field_prompt = query_field_prompt.replace("{field_infos}", str(field))

        lc_messages = self.get_langchain_messages_from_html_tags_in_prompt(query_field_prompt, ['objectifs'])
        promptlate =  ChatPromptTemplate.from_messages(lc_messages)
        # Or version w/o separating prompt's tags into separate messages
        # promptlate = ChatPromptTemplate.from_template(query_field_prompt)

        chain = promptlate | self.llm | RunnablePassthrough()
        response = await Llm.invoke_chain_with_input_async("query form field", chain)
        return Llm.get_content(response)
    
    async def get_group_values_from_text_async(self, group: Group, text: str):
        group_get_values_prompt = file.get_as_str("src/prompts/get_group_values_from_text_answer_prompt.txt")
        fields_infos = []
        for field in group.fields:
            fields_infos.append(f"{field.name}: {field.description}")

        fields_infos_str = "- " + "\n- ".join(fields_infos)
        group_get_values_prompt = group_get_values_prompt.replace("{group_name}", group.name)
        group_get_values_prompt = group_get_values_prompt.replace("{group_desc}", group.description)
        group_get_values_prompt = group_get_values_prompt.replace("{fields_infos}", fields_infos_str)
        group_get_values_prompt = group_get_values_prompt.replace("{text_answer}", text)

        lc_messages = self.get_langchain_messages_from_html_tags_in_prompt(group_get_values_prompt, ['objectifs'])
        promptlate =  ChatPromptTemplate.from_messages(lc_messages)
        # Or version w/o separating prompt's tags into separate messages
        #promptlate = ChatPromptTemplate.from_template(group_get_values_prompt)
        
        chain = promptlate | self.llm | RunnablePassthrough()
        response = await Llm.invoke_chain_with_input_async("get json group values from user answer", chain)
        values_list = Llm.extract_json_from_llm_response(response)
        
        # In case of failure, fallback with output parser
        if values_list is None:
            prompt_for_output_parser, output_parser = Llm.get_prompt_and_json_output_parser(
                group_get_values_prompt,
                StringsListPydantic,
                list[str])
            values_list = await Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks_async("get output parsed group values from user answer", self.llms, output_parser, 5, prompt_for_output_parser)
        
        return values_list
    
    async def get_form_values_from_conversation_async(self, conversation: list[BaseMessage], form: Form):
        group_get_values_prompt = file.get_as_str("src/prompts/get_form_values_from_conversation_prompt.txt")
        full_form_description = []
        full_form_description.append(f'Nom du formulaire: "{form.name}"')
        for group in form.groups:
            full_form_description.append(f'- Groupe "{group.name}" ({group.description}) :')
            for field in group.fields:
                full_form_description.append(f'  - Champ "{field.name}" ({field.description}),')

        full_form_description_str = "\n ".join(full_form_description)
        group_get_values_prompt = group_get_values_prompt.replace("{full_form_description}", full_form_description_str)
        conversation_str = '\n\n'.join([f'{msg.content}' for msg in conversation])
        group_get_values_prompt = group_get_values_prompt.replace("{conversation}", conversation_str)

        lc_messages = self.get_langchain_messages_from_html_tags_in_prompt(group_get_values_prompt, ['objectifs', 'conversation'])
        promptlate =  ChatPromptTemplate.from_messages(lc_messages)
        # Or version w/o separating prompt's tags into separate messages
        #promptlate = ChatPromptTemplate.from_template(group_get_values_prompt)
        
        chain = promptlate | self.llm | RunnablePassthrough()
        response = await Llm.invoke_chain_with_input_async("get form values from conversation", chain)
        values_list = Llm.extract_json_from_llm_response(response)
        
        # In case of failure, fallback with output parser
        if values_list is None:
            prompt_for_output_parser, output_parser = Llm.get_prompt_and_json_output_parser(
                group_get_values_prompt,
                DictListPydantic,
                list[dict[str, str]])
            values_list = await Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks_async("get output parsed group values from user answer", self.llms, output_parser, 5, prompt_for_output_parser)
        
        return values_list
    
    def get_langchain_messages_from_html_tags_in_prompt(self, prompt: str, tags_human_messages: list[str] = []) -> list[BaseMessage]:
        """Get Langchain messages extracted from HTML tags in the provided prompt."""
        messages: list[BaseMessage] = []
        pattern = re.compile(r'<(?P<tag>\w+)>(?P<content>.*?)</(?P=tag)>', re.DOTALL)
        for match in pattern.finditer(prompt):
            tag: str = match.group("tag").strip()
            content: str = match.group("content").strip()
            if tag in tags_human_messages:
                messages.append(HumanMessage(content=content))
            else:
                messages.append(SystemMessage(content=content))
        return messages
