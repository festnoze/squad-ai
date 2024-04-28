from langchains.langchain_adapter import LangChainAdapter
from models.acceptance_criterion import AcceptanceCriterionTestUnit
from langchain.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain.schema.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.messages.base import BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain.pydantic_v1 import BaseModel, Field
from textwrap import dedent
from file_helper import file

class PlanNextActionInputs(BaseModel):
    feature_description: str = Field(..., description="Detailed description of the feature")
    handled_acceptance_criteria: str = Field(..., description="Description of the acceptance criteria that should be handled")

class PlanTddAction:
    @staticmethod
    def plan_next_acceptance_criterion(lc: LangChainAdapter, feature_description: str, implemented_acceptance_criteria: list[AcceptanceCriterionTestUnit], stop_sentence: str) -> AcceptanceCriterionTestUnit:
        tdd_developer_instructions = file.get_as_str("tdd_developer_instructions.txt")
        feature_description_prompt = file.get_as_str("feature_description_prompt.txt").format(feature_description= feature_description)
        acceptance_criterion_creation_prompt = file.get_as_str("acceptance_criterion_creation_prompt.txt").format(handled_acceptance_criteria= ", ".join([acceptance_criterion.description for acceptance_criterion in implemented_acceptance_criteria]))
        
        messages: list[BaseMessage] = [
            SystemMessage(tdd_developer_instructions),
            SystemMessage(feature_description_prompt),
            HumanMessage(acceptance_criterion_creation_prompt),
        ]
        
        acceptance_criterion_desc, elapsed_desc = lc.invoke_with_elapse_time(messages)
        next_criterion = AcceptanceCriterionTestUnit(acceptance_criterion_desc)
        implemented_acceptance_criteria.append(next_criterion)
        return next_criterion


