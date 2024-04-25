from models.acceptance_criterion import AcceptanceCriterion
from langchain.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain.schema.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain.pydantic_v1 import BaseModel, Field
from textwrap import dedent

class PlanNextActionInputs(BaseModel):
    feature_description: str = Field(..., description="Detailed description of the feature")
    handled_acceptance_criteria: str = Field(..., description="Description of the acceptance criteria that should be handled")

class PlanTddAction:
    @staticmethod
    def plan_next_action(llm: any, feature_description: str, implemented_acceptance_criteria: list[AcceptanceCriterion]) -> AcceptanceCriterion:
        tdd_developer_instructions = """\
            You are a senior backend developper, expert in Test Driven Development experienced in C# and python. 
            You're skilled in problem decomposition, in finding the next increment, in finding happy paths and edge cases.
            You're in the know that an acceptance criterion is always triggered by a user action rather than by an internal state of the system."""
        feature_description_prompt = "The global feature we are implementing is the following: {feature_description}."
        acceptance_criterion_prompt = """\
            Given that we already had implemented the following acceptance criteria: {handled_acceptance_criteria}.
            Propose the next unhandled acceptance criterion that should be implemented first."""      
        prompts = ChatPromptTemplate.from_messages(
            [
                SystemMessage(tdd_developer_instructions),
                SystemMessage(feature_description_prompt.format(feature_description=feature_description)),
                HumanMessage(acceptance_criterion_prompt),
            ])        
        inputs = {
            "feature_description": feature_description,
            "handled_acceptance_criteria": RunnablePassthrough()
        }
        
        chain = {"handled_acceptance_criteria": RunnablePassthrough()} | prompts | llm | StrOutputParser()
        acceptance_criterion_desc = chain.invoke(", ".join([acceptance_criterion.description for acceptance_criterion in implemented_acceptance_criteria]))
        
        
        test_name_prompt = ChatPromptTemplate.from_template("return only a name you create in Pascal Case for the unit test corresponding to the following acceptance criterion: {acceptance_criterion}")
        namechain = test_name_prompt | llm | StrOutputParser()
        acceptance_criterion_name = namechain.invoke(acceptance_criterion_desc)

        print("desc: '" + acceptance_criterion_desc + "' , test name: '" + acceptance_criterion_name + "'")
        return AcceptanceCriterion(acceptance_criterion_name, acceptance_criterion_desc)  # Returns the next acceptance criterion or None if all are implemented

