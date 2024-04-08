import asyncio
import openai
import os
from dotenv import find_dotenv, load_dotenv
from collections import namedtuple
# internal import
from orchestrator import Orchestrator
from langchains.langchain_factory import LangChainFactory
from langchains.langchain_adapter_interface import LangChainAdapter
from langchains.langchain_adapter_type import LangChainAdapterType

async def main():
    # Load environment variables from .env file
    load_dotenv(find_dotenv())

    # Access the value of OPEN_API_KEY
    openai_api_key = os.getenv("OPEN_API_KEY")

    # Set the OpenAI API key
    openai.api_key = openai_api_key
    max_exchanges_count = 4

    # List available models
    #import sys
    # ai.print_models()
    # sys.exit()

    # Define named tuple for holding LLM infos: type and model
    LlmInfo = namedtuple('LlmInfo', ['type', 'model', 'api_key'])

    # Select the LLM to be use
    llm_infos = LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4-turbo-preview", api_key= openai_api_key)
    #llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "dolphin-mixtral", api_key= None)
    #llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "llama2", api_key= None)
    #llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "mistral", api_key= None)
    #llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "nous-hermes2", api_key= None)
    #llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "openhermes", api_key= None)

    generic_langchain_adapter = LangChainFactory.get_langchain_adapter(llm_infos.type, llm_infos.model, llm_infos.api_key)
    
    #Start the ochestrator workflow  
    orchestrator = Orchestrator(generic_langchain_adapter, max_exchanges_count)
    try:
        await orchestrator.perform_workflow_async()
        
    except Exception as ex:
        print(ex)
    finally:    
        # orchestrator.dispose()
        print("[Fin de l'échange]")


asyncio.run(main())

