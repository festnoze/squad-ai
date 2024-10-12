import asyncio
import openai
import os
from dotenv import find_dotenv, load_dotenv

from langchains.langchain_adapter_generic import LangChainAdapter

# internal import
from orchestrator import Orchestrator
from common_tools.models.langchain_adapter_type import LangChainAdapterType
from common_tools.models.llm_info import LlmInfo

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
    llms_infos = []
    #llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "phi3", timeout= 80, temperature = 0.5, api_key= None))
    #llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "llama2",  timeout= 200, temperature = 0.5, api_key= None))
    #llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "llama3", timeout= 200, temperature = 0.5, api_key= None))
    #llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "mistral",  timeout= 200, temperature = 0.5, api_key= None))
    #llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "mixtral",  timeout= 500, temperature = 0.5, api_key= None))
    #llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "dolphin-mixtral",  timeout= 400, temperature = 0.5, api_key= None))
    #llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "nous-hermes2", timeout= 200, temperature = 0.5, api_key= None))
    #llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "openhermes", timeout= 200, temperature = 0.5, api_key= None))

    #llms_infos.append(LlmInfo(type= LangChainAdapterType.Groq, model= "mixtral-8x7b-32768",  timeout= 20, temperature = 0.5, api_key= groq_api_key))
    #llms_infos.append(LlmInfo(type= LangChainAdapterType.Groq, model= "llama3-8b-8192",  timeout= 10, temperature = 0.5, api_key= groq_api_key))
    #llms_infos.append(LlmInfo(type= LangChainAdapterType.Groq, model= "llama3-70b-8192",  timeout= 20, temperature = 0.5, api_key= groq_api_key))

    #llms_infos.append(LlmInfo(type= LangChainAdapterType.Google, model= "gemini-pro",  timeout= 60, temperature = 0.5, api_key= google_api_key))

    #llms_infos.append(LlmInfo(type= LangChainAdapterType.Anthropic, model= "claude-2",  timeout= 60, temperature = 0.5, api_key= anthropic_api_key))
    #llms_infos.append(LlmInfo(type= LangChainAdapterType.Anthropic, model= "claude-3-haiku-20240307",  timeout= 60, temperature = 0.5, api_key= anthropic_api_key))
    #llms_infos.append(LlmInfo(type= LangChainAdapterType.Anthropic, model= "claude-3-sonnet-20240229",  timeout= 60, temperature = 0.5, api_key= anthropic_api_key))
    #llms_infos.append(LlmInfo(type= LangChainAdapterType.Anthropic, model= "claude-3-opus-20240229",  timeout= 60, temperature = 0.5, api_key= anthropic_api_key))

    #llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo-0125",  timeout= 60, temperature = 0.5, api_key= openai_api_key))
    #llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo",  timeout= 60, temperature = 0.5, api_key= openai_api_key))
    #llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4-turbo",  timeout= 120, temperature = 0.5, api_key= openai_api_key))
    llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4o",  timeout= 60, temperature = 1, api_key= openai_api_key))
    llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4o",  timeout= 80, temperature = 0.1, api_key= openai_api_key))

    llm_info = llms_infos[-1]
    langchain_adapter = LangChainAdapter(
        adapter_type= llm_info.type,
        llm_model_name= llm_info.model,
        timeout_seconds= llm_info.timeout,
        temperature= llm_info.temperature,
        api_key= llm_info.api_key)
    
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

