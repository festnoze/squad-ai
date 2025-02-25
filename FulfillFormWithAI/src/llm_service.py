
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
from langchain_core.runnables import Runnable, RunnablePassthrough

from models.group import Group

class LlmService:
    def __init__(self, llms_infos: list[LlmInfo] = None):
        if llms_infos is None:
            llms_infos = EnvHelper.get_llms_infos_from_env_config(skip_commented_lines=True)
        self.llms_infos = llms_infos
        self.llms = LangChainFactory.create_llms_from_infos(llms_infos)
        self.llm = self.llms[0]

    async def ask_questions_until_form_is_fulfilled_async(self, form: Form):
        data = {}
        while not form.validate():
            for group in form.groups:
                await self.ask_question_for_group_async(group)
                while not group.validate():

                    for field in group.fields:
                        if field.name not in data:
                            data[field.name] = await self.ask_field_question_async(field)
        return data
    
    async def ask_question_for_group_async(self, group: Group):
        query_group_prompt = file.get_as_str("src/prompts/query_group_prompt.txt")
        fields_infos = []
        for field in group.fields:
            fields_infos.append(f"{field.name}: {field.description}")
        fields_infos_str = "- " + "\n- ".join(fields_infos)
        query_group_prompt = query_group_prompt.replace("<group_name>", group.name)
        query_group_prompt = query_group_prompt.replace("<group_desc>", group.description)
        query_group_prompt = query_group_prompt.replace("<fields_infos>", fields_infos_str)
        promptlate = ChatPromptTemplate.from_template(query_group_prompt)
        chain = promptlate | self.llm | RunnablePassthrough()
        response = await Llm.invoke_chain_with_input_async("query form group", chain)
        return Llm.get_content(response)
    
    async def ask_field_question_async(self, field: Field):
        query_field_prompt = file.get_as_str("src/prompts/query_field_prompt.txt")
        query_field_prompt = query_field_prompt.replace("<field_name>", field.name)
        query_field_prompt = query_field_prompt.replace("<field_desc>", field.description)
        query_field_prompt = query_field_prompt.replace("<field_infos>", str(field))

        promptlate = ChatPromptTemplate.from_template(query_field_prompt)
        chain = promptlate | self.llm | RunnablePassthrough()
        response = await Llm.invoke_chain_with_input_async("query form field", chain)
        return Llm.get_content(response)