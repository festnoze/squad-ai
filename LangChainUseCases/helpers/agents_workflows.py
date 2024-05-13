from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.output_parsers import StrOutputParser, ListOutputParser, MarkdownListOutputParser, JsonOutputParser
from typing import TypeVar, Generic, Any

from helpers.txt_helper import txt

def invoke_llm_with_retry(llm, input, max_retries=3):
    for i in range(max_retries):
        try:
            result = llm.invoke(input)
            return txt.get_llm_answer_content(result)
        except Exception as e:
            print(f"Error: {e}")
            print(f"Retrying... {i+1}/{max_retries}")
    raise Exception(f"LLM failed. Stopped after {max_retries} retries")


TPydanticModel = TypeVar('TPydanticModel', bound=BaseModel)    
TOutputModel = TypeVar('TOutputModel')

def invoke_llm_with_json_output_parser(llm: BaseChatModel, prompt_str: str, json_type: TPydanticModel, output_type: TOutputModel, max_retries= None) -> TOutputModel:
    assert issubclass(json_type, BaseModel), "json_type must inherit from BaseModel"
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "Process the following input, then create a JSON object respecting those formating instructions: {formating_instructions}"),
            ("human", "{input}"),
        ]
    )
    
    parser = JsonOutputParser(pydantic_object=json_type)
    chain = prompt | llm | parser
    input = {
        "input": prompt_str,
        "formating_instructions": parser.get_format_instructions()
    }

    if max_retries:
        result = invoke_llm_with_retry(chain, input, max_retries)
    else:
        result = chain.invoke(input)

    # transform the result's dict into the awaited type
    result_obj = output_type(**result)
    return result_obj