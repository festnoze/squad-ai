from langchain_core.language_models import BaseChatModel
from langchain.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain.schema.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.messages.base import BaseMessage
from models.acceptance_criterion import AcceptanceCriterionTestUnit
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain.pydantic_v1 import BaseModel, Field
from textwrap import dedent
from file_helper import file

class WriteTest:
    @staticmethod    
    def create_test_name(llm: BaseChatModel, acceptance_criterion_unit: AcceptanceCriterionTestUnit): 
        tdd_developer_instructions = file.get_as_str("tdd_developer_instructions.txt")       
        test_name_creation_instructions = file.get_as_str("test_name_creation_instructions.txt")
        test_name_creation_prompt = "Create a name for the unit test corresponding to the following acceptance criterion: '{acceptance_criterion_desc}'.".format(acceptance_criterion_desc= acceptance_criterion_unit.acceptance_criterion_desc)
        
        messages: list[BaseMessage] = [
            SystemMessage(tdd_developer_instructions),
            SystemMessage(test_name_creation_instructions),
            HumanMessage(test_name_creation_prompt),
        ]

        acceptance_criterion_name = llm.invoke(messages)
        acceptance_criterion_unit.unittest_name = acceptance_criterion_name
        
    def create_test_gherkin(llm: BaseChatModel, acceptance_criterion_unit: AcceptanceCriterionTestUnit):
        tdd_developer_instructions = file.get_as_str("tdd_developer_instructions.txt")
        write_gherkin_test_instructions = file.get_as_str("write_gherkin_test_instructions.txt")
        gherkin_creation_prompt = file.get_as_str("gherkin_creation_prompt.txt").format(acceptance_criterion_description= acceptance_criterion_unit.acceptance_criterion_desc)
                
        messages: list[BaseMessage] = [
            SystemMessage(tdd_developer_instructions),
            SystemMessage(write_gherkin_test_instructions),
            HumanMessage(gherkin_creation_prompt),
        ]
        
        gherkin_code = llm.invoke(messages)
        acceptance_criterion_unit.gherkin_code = gherkin_code

    def design_test(llm: BaseChatModel, acceptance_criterion_unit: AcceptanceCriterionTestUnit):
        prompt = """\
            Given the following acceptance criterion: '{acceptance_criterion_desc}'.
            List what ... TODO?
            """

    @staticmethod
    def write_unittest_code(llm: BaseChatModel, acceptance_criterion_unit: AcceptanceCriterionTestUnit):
        tdd_developer_instructions = file.get_as_str("tdd_developer_instructions.txt")
        write_unittest_instructions = file.get_as_str("write_unittest_instructions.txt")
        unittest_creation_prompt = file.get_as_str("unittest_creation_prompt.txt").format(acceptance_criterion_description= acceptance_criterion_unit.acceptance_criterion_desc)
                
        messages: list[BaseMessage] = [
            SystemMessage(tdd_developer_instructions),
            SystemMessage(write_unittest_instructions),
            HumanMessage(unittest_creation_prompt),
        ]
        
        gherkin_code = llm.invoke(messages)
        acceptance_criterion_unit.gherkin_code = gherkin_code

    @staticmethod
    def ensure_test_fails(llm: BaseChatModel, test_code: str):
        pass
