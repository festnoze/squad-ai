from typing import List
from langchains.langchain_adapter import LangChainAdapter
from models.acceptance_criterion import AcceptanceCriterion
from langchain.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain.schema.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.messages.base import BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain.pydantic_v1 import BaseModel, Field
from textwrap import dedent

class PlanNextActionInputs(BaseModel):
    feature_description: str = Field(..., description="Detailed description of the feature")
    handled_acceptance_criteria: str = Field(..., description="Description of the acceptance criteria that should be handled")

class PlanTddAction:
    @staticmethod
    def plan_next_action(lc: LangChainAdapter, feature_description: str, implemented_acceptance_criteria: list[AcceptanceCriterion], stop_sentence: str) -> AcceptanceCriterion:
        # Prompts
        tdd_developer_instructions = """\
            You are a senior backend developper, expert in Test Driven Development experienced in C# and python. 
            You're skilled in problem decomposition, in finding the next increment, in finding happy paths and edge cases.
            You're in the know that an acceptance criterion is always triggered by a user action rather than by an internal state of the system.
            As an experienced TDD developer, you always begin with the most trivial actions, parsing all edge cases or values before moving to the core feature criterions."""
        
        create_feature_description_prompt = "The global feature we are implementing is the following: {feature_description}."

        create_acceptance_criterion_prompt = """\
            Given that we already had implemented the following acceptance criteria: {handled_acceptance_criteria}.
            Propose the next single acceptance criterion which is unhandled and should be implemented first. 
            Ifever, you don't find any acceptance criterion left to implement, just write: '""" + stop_sentence + """'.
            Otherwise, write only the content of the description of the acceptance criterion without any other words added, just a concise description. Don't mention the feature itself as we know the context. Focus on the behavior/result awaited when performing an action under specific conditions (or data).
            For example, if the feature is: implement a string calculator, an example of well formated acceptance criterion could be : 'an empty string input should return 0 as result'. 
            A bad example for the same criterion would be: 'Acceptance Criterion: Test that the string calculator can handle a string which is empty, then returned result should be 0 (e.g., '') """
        
        create_test_name_prompt = """\
            Create a name for the unit test corresponding to the following acceptance criterion: '{acceptance_criterion}'.
            Follow the following rules for this test name creation:
            - return only the test's name, nothing else, no introduction, no description afterwards,
            - create it using Pascal Casing,
            - each following summary should be less than 4 words long, avoiding articles, always in pascal case,
            - whenever it's relevent and needed for the understanding, begin test's name with the context or conditions formated like this: a summary of this context or conditions, then add an underscore 
            - then add a summary of the action (corresponds to the 'Act'/'When' part of the test), then add an underscore 
            - followed by 'Should', then a summary of either the awaited output, either the awaited state - which can simply be 'Succeed' (or 'Fail_WithErrorX' for an awaited error)-,
            - always finished the name creation adding an underscore, then: 'Test'"""
        
        handled_acceptance_criteria = ", ".join([acceptance_criterion.description for acceptance_criterion in implemented_acceptance_criteria])
        messages: List[BaseMessage] = [
            SystemMessage(dedent(tdd_developer_instructions)),
            SystemMessage(dedent(create_feature_description_prompt.format(feature_description= feature_description))),
            HumanMessage(dedent(create_acceptance_criterion_prompt.format(handled_acceptance_criteria= handled_acceptance_criteria))),
        ]
        
        acceptance_criterion_desc, elapsed_desc = lc.invoke_with_elapse_time(messages)        
        print(f"-- Elapsed: {elapsed_desc}s. --")

        test_name_prompt_template = ChatPromptTemplate.from_template(dedent(create_test_name_prompt))
        test_name_chain = test_name_prompt_template | lc.llm | StrOutputParser()

        acceptance_criterion_name = test_name_chain.invoke(acceptance_criterion_desc)

        return AcceptanceCriterion(acceptance_criterion_name, acceptance_criterion_desc)  # Returns the next acceptance criterion or None if all are implemented

