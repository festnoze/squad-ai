import asyncio
import openai
import os
from dotenv import find_dotenv, load_dotenv
from collections import namedtuple
# internal import
from orchestrator import Orchestrator
from langchains.langchain_adapter_type import LangChainAdapterType
from langchains.langchain_adapter_generic import LangChainAdapter

async def main():
    # Load environment variables from .env file
    load_dotenv(find_dotenv())

    # Access the value of OPEN_API_KEY
    openai_api_key = os.getenv("OPEN_API_KEY")

    # Set the OpenAI API key
    openai.api_key = openai_api_key
    max_exchanges_count = 4

    # # List available models
    # import sys
    # from openai_helper import ai
    # ai.print_models()
    # sys.exit()

    # Define named tuple for holding LLM infos: type and model
    LlmInfo = namedtuple('LlmInfo', ['type', 'model', 'api_key'])

    # Select the LLM to be use
    llm_infos = LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo-0613", api_key= openai_api_key)
    #llm_infos = LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4-turbo-preview", api_key= openai_api_key)
    #llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "dolphin-mixtral", api_key= None)
    #llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "llama2", api_key= None)
    #llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "mistral", api_key= None)
    #llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "nous-hermes2", api_key= None)
    #llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "openhermes", api_key= None)

    langchain_adapter = LangChainAdapter(
        adapter_type= llm_infos.type,
        llm_model_name= llm_infos.model,
        timeout_seconds= 100,
        temperature= 0.1,
        api_key= llm_infos.api_key)
    
    #Start the ochestrator workflow  
    orchestrator = Orchestrator(langchain_adapter, max_exchanges_count)
    try:
        await orchestrator.perform_workflow_async()
        
    except Exception as ex:
        print(ex)
    finally:    
        # orchestrator.dispose()
        print("[Fin de l'échange]")


asyncio.run(main())

