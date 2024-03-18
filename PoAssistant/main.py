import asyncio
import openai
import os
import sys
from misc import misc
from file import file
from dotenv import find_dotenv, load_dotenv
from ochestrator import assistants_ochestrator
#from langchain import langchain

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
    max_exchanges_count = 5

    #define the need and send it to the ochestrator
    need_file = "need.txt"
    file.delete_file(need_file)
    misc.wait_until_need_file_is_created()
    need = file.get_as_str(need_file)
    print(f"Description initiale de l'objectif : {need}")
    
    orchestrator = assistants_ochestrator(need, max_exchanges_count)
    try:
        orchestrator.create_assistants()
        orchestrator.print_assistants_ids()        

        await orchestrator.perform_workflow_async()

    except Exception as ex:
        print(ex)
    finally:    
        orchestrator.dispose()
        print("[Fin de l'échange]")


asyncio.run(main())

