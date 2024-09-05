from typing import List
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.output_parsers import StrOutputParser, ListOutputParser, MarkdownListOutputParser, JsonOutputParser, BaseTransformOutputParser
from langchain.schema.runnable import Runnable, RunnableParallel, RunnableSequence
from langchain.chains.base import Chain
from langchain.agents import AgentExecutor, create_tool_calling_agent, create_json_chat_agent, tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.callbacks import get_openai_callback, OpenAICallbackHandler
from langchain.schema.messages import HumanMessage, AIMessage, SystemMessage
from helpers.file_helper import file
from helpers.llm_helper import Llm
from models.coding_guidelines_broken_rules_model import Coding_Guidelines_BrokenRules_Model, Coding_Guidelines_BrokenRules_ModelPydantic
from models.coding_guidelines_rule_model import Coding_Guidelines_Rules_Model
from langsmith.schemas import Example, Run
from langsmith.evaluation import evaluate

class CSharpCodeReviewer:
    def __init__(self, llms: List[BaseChatModel]):
        self.llms = llms

    def load_coding_guidelines(self) -> Coding_Guidelines_Rules_Model:
        json = file.get_as_json("coding_guidelines_rules_list.json")
        return Coding_Guidelines_Rules_Model(**json)

    def review_code_dict(self, inputs: dict) -> Coding_Guidelines_BrokenRules_Model:
        res = self.review_code(inputs["input"])
        return res
    
    def review_code(self, code: str) -> Coding_Guidelines_BrokenRules_Model:
        coding_guidelines = self.load_coding_guidelines()
        instructions_prompt = file.get_as_str("csharp_code_review_instructions_prompt.txt")
        coding_guidelines_prompt = file.get_as_str("csharp_code_review_coding_guidelines_prompt.txt")
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", instructions_prompt),
                ("system", coding_guidelines_prompt),
                ("system", "Process the following input, then create a JSON object respecting those formating instructions: {" + Llm.output_parser_instructions_name + "}"),
                ("human", "{code}"),
            ]
        )

        inputs = {
            "stack": "backend, with this stack: .NET and C#", 
            "coding_guidelines": str(coding_guidelines),
            "code": code
        }

        response = Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks("code_review", self.llms, JsonOutputParser(pydantic_object=Coding_Guidelines_BrokenRules_ModelPydantic), None, inputs, prompt)
        answer = Llm.get_llm_answer_content(response[0])
        broken_rules = Coding_Guidelines_BrokenRules_Model(**answer)
        return broken_rules
    
    def contains_match(run: Run, example: Example) -> dict:
        reference = example.outputs["output"]
        prediction = run.outputs["output"]
        score = prediction.lower().contains(reference.lower())
        return {"key": "contains_match", "score": score}
    
    def evaluate_code_review(self) -> dict:
        dataset_name = "ds-csharp-reviewer-01"
        results = evaluate(
            self.review_code,
            data=dataset_name,
            evaluators=[CSharpCodeReviewer.contains_match],
        )
        return results