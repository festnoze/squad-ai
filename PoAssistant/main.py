import asyncio
import openai
import os
import sys
from dotenv import find_dotenv, load_dotenv
from ochestrator import assistants_ochestrator

async def main():
    # Load environment variables from .env file
    load_dotenv(find_dotenv())

    # Access the value of OPEN_API_KEY
    openai_api_key = os.getenv("OPEN_API_KEY")

    # Set the OpenAI API key
    openai.api_key = openai_api_key

    # List available models
    # ai.print_models()
    # sys.exit()
    max_exchanges_count = 5

    #define the need and send it to the ochestrator
    #need = "je souhaiterais afficher les informations administratives de l'utilisateur"
    need= "je souhaiterais créer un module de messagerie pour que les apprenants puisse communiquer entre eux, mais aussi avec des officiels"
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

