# internal import
import time
from helpers.file_helper import file
from helpers.test_helpers import test_agent_executor_with_tools, test_parallel_chains_invocations_with_imputs, test_parallel_invocations_with_homemade_parallel_chains_invocations, test_parallel_invocations_with_homemade_parallel_prompts_invocations
from helpers.txt_helper import txt
from langchains.langchain_factory import LangChainFactory
from langchains.langchain_adapter_type import LangChainAdapterType
from models.llm_info import LlmInfo
from summarize import Summarize
from helpers.groq_helper import GroqHelper

# external imports
import openai
import os
from dotenv import find_dotenv, load_dotenv
import yfinance as yf
from langchain_community.callbacks import get_openai_callback, OpenAICallbackHandler

# Text splitters
from langchain.text_splitter import CharacterTextSplitter
from langchain_community.document_loaders import TextLoader

# Load environment variables from .env file
print("Started")

load_dotenv(find_dotenv())

# Set api keys
groq_api_key = os.getenv("GROQ_API_KEY")
openai_api_key = os.getenv("OPEN_API_KEY")
openai.api_key = openai_api_key

# models = openai.models.list()
# for model in models:
#     print(model.id)
# exit()

# Select the LLM to be used
#llm_infos = LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo-0613",  timeout= 60, api_key= openai_api_key)
#llm_infos = LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4-turbo-2024-04-09",  timeout= 120, api_key= openai_api_key)
llm_infos = LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4o",  timeout= 60, api_key= openai_api_key)

#llm_infos = LlmInfo(type= LangChainAdapterType.Groq, model= "mixtral-8x7b-32768",  timeout= 20, api_key= groq_api_key)
#llm_infos = LlmInfo(type= LangChainAdapterType.Groq, model= "llama3-8b-8192",  timeout= 10, api_key= groq_api_key)
#llm_infos = LlmInfo(type= LangChainAdapterType.Groq, model= "llama3-70b-8192",  timeout= 20, api_key= groq_api_key)

#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "phi3", timeout= 20, api_key= None)
#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "llama3", timeout= 200, api_key= None)
#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "llama2",  timeout= 200, api_key= None)
#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "mistral",  timeout= 200, api_key= None)
#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "mixtral",  timeout= 500, api_key= None)
#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "dolphin-mixtral",  timeout= 400, api_key= None)
#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "nous-hermes2", timeout= 200, api_key= None)
#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "openhermes", timeout= 200, api_key= None)

def run_main():
    # Instanciate the LLM
    llm = LangChainFactory.create_llm(
        adapter_type= llm_infos.type,
        llm_model_name= llm_infos.model,
        timeout_seconds= llm_infos.timeout,
        temperature= 1.0,
        api_key= llm_infos.api_key)
    
    # Test Groq through its own client (no langchain)
    GroqHelper.test_query(llm_infos)

    # Test paralell invocations
    test_parallel_invocations_with_homemade_parallel_prompts_invocations(llm)
    test_parallel_invocations_with_homemade_parallel_chains_invocations(llm)
    test_parallel_chains_invocations_with_imputs(llm)

    ## Use web search tool
    from langchain_community.utilities import GoogleSerperAPIWrapper
    web_search = GoogleSerperAPIWrapper()
    res = web_search.run("what's Obama's first name?")
    print(res)

    ## Use tools through agent executor
    test_agent_executor_with_tools(llm)

    # Summarize short text
    text = file.get_as_str("short-text.txt")
    res = Summarize.summarize_short_text(llm, text)

    # Summarize long text
    text = file.get_as_str("LLM agents PhD thesis full.txt")
    res = Summarize.summarize_long_text(llm, text, 15000)

def get_eur_usd_rate():
    ticker = yf.Ticker("EURUSD=X")
    data = ticker.history(period="1d")
    rate = data["Close"].iloc[-1]
    return rate

def display_tokens_consumtion(cb: OpenAICallbackHandler):
    max_len = max(len(str(cb.completion_tokens)), len(str(cb.prompt_tokens)), len(str(cb.total_tokens)))
    print(f"Prompt Tokens:       {cb.prompt_tokens}")
    print(f"Completion Tokens: + {cb.completion_tokens}")    
    print(f"                     " + "-" * max_len)
    print(f"Total Tokens:        {cb.total_tokens}")
    print(f"Cost:                {cb.total_cost / get_eur_usd_rate():.3f}€ ({cb.total_cost:.3f}$)")
    print(f"(Cost by 1M token:   {(1000000 * cb.total_cost / cb.total_tokens):.3f}$)")   

with get_openai_callback() as openai_callback:
    run_main()
    if llm_infos.type == LangChainAdapterType.OpenAI:
        display_tokens_consumtion(openai_callback)