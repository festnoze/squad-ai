# internal import
from helpers.langgraph_llm_generated_code_execution import LangGraphLlmGeneratedCodeExecution
from helpers.langgraph_tools_supervisor import LangGraphToolsSupervisor
from helpers.test_helpers import test_agent_executor_with_tools, test_parallel_chains_invocations_with_imputs, test_parallel_invocations_with_homemade_parallel_chains_invocations, test_parallel_invocations_with_homemade_parallel_prompts_invocations

# common tools imports
from common_tools.helpers.file_helper import file
from common_tools.models.file_already_exists_policy import FileAlreadyExistsPolicy
from common_tools.helpers.file_helper import file
from common_tools.helpers.llm_helper import Llm
from common_tools.helpers.tools_helpers import MathToolBox, RandomToolBox, WordsToolBox
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.groq_helper import GroqHelper
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.models.langchain_adapter_type import LangChainAdapterType
from common_tools.models.langgraph_agent_state import AgentState
from common_tools.langchains.langsmith_client import Langsmith
from common_tools.models.llm_info import LlmInfo
from common_tools.helpers.env_helper import EnvHelper

# external imports
import json
from csharp_code_reviewer import CSharpCodeReviewer
#from drupaljsonapi import DrupalJsonApiClient
from function_call_examples import FunctionCallExamples
from langchain_community.callbacks import get_openai_callback, OpenAICallbackHandler
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from summarize import Summarize
from langchain_community.retrievers import BM25Retriever
import openai
import os
from dotenv import find_dotenv, load_dotenv
import asyncio
#import yfinance as yf

async def main_async(): 
    # Load environment variables from .env file
    print("Starting...")

    load_dotenv(find_dotenv())

    # Set api keys
    groq_api_key = os.getenv("GROQ_API_KEY")
    openai_api_key = os.getenv("OPEN_API_KEY")
    google_api_key = os.getenv("GOOGLE_API_KEY")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    openai.api_key = openai_api_key

    # models = openai.models.list()
    # for model in models:
    #     print(model.id)
    # exit()

    langsmith = Langsmith()
    langsmith.create_project()

    txt.activate_print = True
    llms_infos = EnvHelper.get_llms_infos_from_env_config()

    #Examples of resolution with agent and tools or code generation
    #FunctionCallExamples.resolve_using_llm_direct(llms_infos)
    #await FunctionCallExamples.resolve_using_agent_executor_with_tools_async(llms_infos)
    await FunctionCallExamples.resolve_using_native_single_tool_call_async(llms_infos)
    # FunctionCallExamples.resolve_using_agent_with_manual_tool_call_in_graph(llms_infos)
    # FunctionCallExamples.resolve_using_langchain_tool_call(llms_infos)

    # FunctionCallExamples.resolve_using_codeact_code_execution(llms_infos)

    # Use tools through agent executor
    llm = LangChainFactory.create_llms_from_infos(llms_infos)[0]
    test_agent_executor_with_tools(llm)
    
    # # Test BM25 retriever
    # rag_structs_summaries_csv = "outputs/rag_structs_summaries.csv"
    # documents = file.read_csv(rag_structs_summaries_csv)
    # documents = [doc[0] for doc in documents]

    # bm25_retriever = BM25Retriever.from_texts(documents)
    # bm25_retriever.k = 7

    # results = bm25_retriever.invoke("Which method speak about answers?")
    # for result in results:
    #     print(result.page_content)
    #     print("----")
    # exit()

    # #Test Groq through its own client (no langchain)
    # GroqHelper.test_query(llms_infos[0])

    # # Test code review
    # llms = LangChainFactory.create_llms_from_infos(llms_infos)
    # code_review = CSharpCodeReviewer(llms)
    # code = file.get_as_str("FunderIto.cs")
    # examples = langsmith.get_dataset_examples("ds-csharp-reviewer-01")
    # for example in examples:
    #     print(example["input"])
    #     print(example["output"])
    #     print("----")
    #     broken_rules = code_review.review_code(code)
    #     print(str(broken_rules))
        
    # code_review.evaluate_code_review()
    # exit()

    # # Test parallel invocations
    # llm = LangChainFactory.create_llms_from_infos(llms_infos)[0]
    # test_parallel_invocations_with_homemade_parallel_prompts_invocations(llm)
    # test_parallel_invocations_with_homemade_parallel_chains_invocations(llm)
    # test_parallel_chains_invocations_with_imputs(llm)

    # # Use web search tool
    # from langchain_community.utilities import GoogleSerperAPIWrapper
    # web_search = GoogleSerperAPIWrapper()
    # res = web_search.run("what's Obama's first name?")
    # print(res)

    # # Summarize short text
    # llm = LangChainFactory.create_llms_from_infos(llms_infos)[0]
    # text = file.get_as_str("short-text.txt")
    # res = Summarize.summarize_short_text(llm, text)

    # # Summarize long text
    # text = file.get_as_str("LLM agents PhD thesis full.txt")
    # res = Summarize.summarize_long_text(llm, text, 15000)
    

def main():
    asyncio.run(main_async())

main()