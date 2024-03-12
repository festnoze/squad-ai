import openai
import os
import sys
from dotenv import find_dotenv, load_dotenv
from openai_helper import ai
from display_helper import display
from AssistantSet import AssistantSet
from misc import misc
from ochestrator import assistants_ochestrator

# Load environment variables from .env file
load_dotenv(find_dotenv())

# Access the value of OPEN_API_KEY
openai_api_key = os.getenv("OPEN_API_KEY")

# Set the OpenAI API key
openai.api_key = openai_api_key

# List available models
# ai.print_models()
# sys.exit()

model = "gpt-4-turbo-preview"#"gpt-3.5-turbo-16k"

# Assistants creation
moa_assistant = ai.create_assistant_set(
    model= model, 
    instructions= misc.get_str_file("moa_assistant_instructions.txt"),
    run_instructions = misc.get_str_file("moa_run_instructions.txt")
)
moe_assistant = ai.create_assistant_set(
    model= model, 
    instructions= misc.get_str_file("moe_assistant_instructions.txt"),
    run_instructions = misc.get_str_file("moe_run_instructions.txt")
)

display.display_ids("MOA", moa_assistant)
display.display_ids("MOE", moe_assistant)

try:
    #define the need and send it to the ochestrator
    need= "je souhaiterais créer un module de messagerie pour que les apprenants puisse communiquer entre eux, mais aussi avec des officiels"
    #need = "je souhaiterais afficher les informations administratives de l'utilisateur"
    output = assistants_ochestrator(need, moe_assistant, moa_assistant)
except Exception as ex:
    print(ex)
finally:    
    ai.delete_assistant_set(moe_assistant)
    ai.delete_assistant_set(moa_assistant)
    #ai.delete_all_assistants()
    print("[Fin de l'échange]")

