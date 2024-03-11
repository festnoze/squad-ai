import openai
import os
from dotenv import find_dotenv, load_dotenv
from openai_helper import ai
from display_helper import display
from AssistantSet import AssistantSet, AssistantSetIds
from ochestrator import assistants_ochestrator

# Load environment variables from .env file
load_dotenv(find_dotenv())

# Access the value of OPEN_API_KEY
openai_api_key = os.getenv("OPEN_API_KEY")

# Set the OpenAI API key
openai.api_key = openai_api_key

# List available models
# models = openai.models.list()
# for model in models:
#     print("model: ", model.id)
# sys.exit()

model = "gpt-3.5-turbo-16k"
moa_assistant_infos = AssistantSetIds(
    assistant_id= "asst_6sexVznA5YHOtY7SXNfX12HX",
    thread_id= "thread_xgHIbYTaaqdiVvq7TKUp0lOy",
    run_id= "run_CZdbwVcIHVgzjs4SqfgfQS1M"
)

moe_assistant_infos = AssistantSetIds(
    assistant_id= "asst_pUTwZcNLyC6co5uuAfJzfSYS",
    thread_id= "thread_fzyerG2D75xxfKveNX3LjA9n",
    run_id= "run_93ZYlRQCnkG6653L9Hbf9Wdz"
)

# Assistant creation
# do_create_assistant = input("Create assistants? (C)reate, (R)euse, (N)ew thread")
# if do_create_assistant == "c":
moa_assistant = ai.create_full_assistant(
    model= model, 
    instructions= ai.str_file("moa_assistant_instructions.txt"),
    run_instructions= ai.str_file("moa_run_instructions.txt")
)
moe_assistant = ai.create_full_assistant(
    model= model, 
    instructions= ai.str_file("moe_assistant_instructions.txt"),
    run_instructions= ai.str_file("moa_run_instructions.txt")
    #message= ""
)
# elif do_create_assistant == "r":
#     moa_assistant = AssistantModel.create_from_ids(moa_assistant_infos)
#     moe_assistant = AssistantModel.create_from_ids(moe_assistant_infos)
# else:
    # moa_assistant = ai.create_new_thread_on_existing_assistant(moa_assistant_infos.assistant_id)
    # moe_assistant = ai.create_new_thread_on_existing_assistant(moe_assistant_infos.assistant_id)

display.display_ids("MOA", moa_assistant)
display.display_ids("MOE", moe_assistant)

try:
    #define the need
    ai.pause(1)
    message= "je souhaiterais créer un module de messagerie pour que les apprenants puisse communiquer entre eux, mais aussi avec des officiels"
    output = assistants_ochestrator(message, moe_assistant, moa_assistant)
    print(output)
except Exception as ex:
    print(ex)
finally:
    ai.delete_assistant_set(moe_assistant)
    ai.delete_assistant_set(moa_assistant)

