import openai
import os
from collections import namedtuple
from dotenv import find_dotenv, load_dotenv
from tdd_workflow import TddWorkflow
from langchains.langchain_adapter_type import LangChainAdapterType
from langchains.langchain_adapter import LangChainAdapter

load_dotenv(find_dotenv())
openai_api_key = os.getenv("OPEN_API_KEY")
openai.api_key = openai_api_key

groq_api_key = os.getenv("GROQ_API_KEY")

# Define named tuple for holding LLM infos: type and model
LlmInfo = namedtuple('LlmInfo', ['type', 'model', 'timeout', 'api_key'])

# Select the LLM to be used
#llm_infos = LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo-0613",  timeout= 60, api_key= openai_api_key)
#llm_infos = LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4-turbo-2024-04-09",  timeout= 120, api_key= openai_api_key)

#llm_infos = LlmInfo(type= LangChainAdapterType.Groq, model= "llama3-70b-8192",  timeout= 20, api_key= groq_api_key)

llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "phi3", timeout= 20, api_key= None)
#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "llama3", timeout= 100, api_key= None)
#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "llama2",  timeout= 200, api_key= None)
#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "mistral",  timeout= 200, api_key= None)
#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "dolphin-mixtral",  timeout= 400, api_key= None)
#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "nous-hermes2", timeout= 200, api_key= None)
#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "openhermes", timeout= 200, api_key= None)

langchain_adapter = LangChainAdapter(
    adapter_type= llm_infos.type,
    llm_model_name= llm_infos.model,
    timeout_seconds= llm_infos.timeout,
    temperature= 0.1,
    api_key= llm_infos.api_key)

feature_desc = "Create a string calculator feature" 
tests, code = TddWorkflow().write_feature_code_using_tdd(langchain_adapter, feature_desc)