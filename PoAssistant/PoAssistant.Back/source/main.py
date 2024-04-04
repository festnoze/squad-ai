import asyncio
import openai
import os
from dotenv import find_dotenv, load_dotenv
from langchain_openai_adapter import lc
#from langchain_ollama_adapter import lc
#from langchain import langchain
# internal import
from orchestrator import Orchestrator
from misc import misc
from file_helper import file

async def main():
    # Load environment variables from .env file
    load_dotenv(find_dotenv())

    # Access the value of OPEN_API_KEY
    openai_api_key = os.getenv("OPEN_API_KEY")

    # Set the OpenAI API key
    openai.api_key = openai_api_key

    #response = langchain.create_openai_assistant("what the wheather in {topic}", "lattes")

    # List available models
    # ai.print_models()
    # sys.exit()
    max_exchanges_count = 2

    #Start the ochestrator workflow  
    lc.set_api_key(openai_api_key)
    orchestrator = Orchestrator(max_exchanges_count)
    try:
        await orchestrator.perform_workflow_async()
        
    except Exception as ex:
        print(ex)
    finally:    
        # orchestrator.dispose()
        print("[Fin de l'échange]")


asyncio.run(main())

