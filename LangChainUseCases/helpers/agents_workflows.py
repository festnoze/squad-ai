import inspect
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.output_parsers import StrOutputParser, ListOutputParser, MarkdownListOutputParser, JsonOutputParser
from langchain.schema.runnable import RunnableParallel

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
    assert inspect.isclass(output_type), "output_type must be a class"

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
    # the awaited type must have an 'init' method that takes the dict as kwargs
    result_obj = output_type(**result)
    return result_obj

def invoke_parallel_prompts(llm: BaseChatModel, *prompts: str) -> list[str]:        
    # Define different chains, assume both use {topic} in their templates
    chains = []
    for prompt in prompts:
        chains.append(ChatPromptTemplate.from_template(prompt) | llm)

    # Combine chains for parallel execution
    combined = RunnableParallel(**{f"invoke_{i}": chain for i, chain in enumerate(chains)})

    # Invoke the combined chain with specific inputs for each chain
    responses = combined.invoke({"topic": ""})

    # Retrieve and print the output from each chain
    responses_list = [responses[key] for key in responses.keys()]
    answers = [txt.get_llm_answer_content(response) for response in responses_list]
    return answers