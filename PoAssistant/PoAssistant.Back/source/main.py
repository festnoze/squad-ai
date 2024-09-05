import asyncio
import openai
import os
from dotenv import find_dotenv, load_dotenv
# internal import
from orchestrator import Orchestrator
from langchains.langchain_adapter_type import LangChainAdapterType
from langchains.langchain_adapter_generic import LangChainAdapter
from models.llm_info import LlmInfo

async def main():
    # Load environment variables from .env file
    load_dotenv(find_dotenv())

    # Set api keys
    groq_api_key = os.getenv("GROQ_API_KEY")
    openai_api_key = os.getenv("OPEN_API_KEY")
    openai.api_key = openai_api_key

    # Set the OpenAI API key
    max_exchanges_count = 4

    # # List available models
    # import sys
    # from openai_helper import ai
    # ai.print_models()
    # sys.exit()

    # Select the LLM to be used
    #llm_infos = LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo-0613",  timeout= 60, api_key= openai_api_key)
    #llm_infos = LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4-turbo-2024-04-09",  timeout= 120, api_key= openai_api_key)

    llm_infos = LlmInfo(type= LangChainAdapterType.Groq, model= "mixtral-8x7b-32768",  timeout= 20, api_key= groq_api_key)
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

    langchain_adapter = LangChainAdapter(
        adapter_type= llm_infos.type,
        llm_model_name= llm_infos.model,
        timeout_seconds= llm_infos.timeout,
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

