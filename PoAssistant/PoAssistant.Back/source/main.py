import asyncio
import openai
import os
from dotenv import find_dotenv, load_dotenv
# internal import
from orchestrator import Orchestrator
from misc import misc
from file_helper import file
from langchain_adapter_interface import LangChainAdapter
from langchain_factory import LangChainFactory

async def main():
    # Load environment variables from .env file
    load_dotenv(find_dotenv())

    # Access the value of OPEN_API_KEY
    openai_api_key = os.getenv("OPEN_API_KEY")

    # Set the OpenAI API key
    openai.api_key = openai_api_key
    max_exchanges_count = 4

    # List available models
    # ai.print_models()
    # sys.exit()

    langchain_adapter = LangChainFactory.get_langchain_adapter("OpenAI")
    #langchain_adapter = LangChainFactory.get_langchain_adapter("Ollama")

    langchain_adapter.set_api_key(openai_api_key)

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

