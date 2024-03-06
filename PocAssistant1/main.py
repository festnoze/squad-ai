import openai
import os
#import sys
from dotenv import find_dotenv, load_dotenv
from helpers import ai
from AssistModel import AssistantModel, AssistantIdsModel

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
assistant_ids = AssistantIdsModel(
    assistant_id= "asst_35c92DNd2Cu5MzTw2wfh4i2J",
    thread_id= "thread_M0qkgndwCTKvRmqHzec2GkuC",
    run_id= "run_SGVZKsDerWKW789Wq6KHAkdg"
)

# Assistant creation
do_create_assistant = input("Create a new assistant? y/n ")
if do_create_assistant == "y":
    assistant_infos = ai.create_full_assistant(
        model= model, 
        instructions= """ you return response in french whatever the language the user input""",
        run_instructions= "write an accessible answer in less than 100 words",
        message= "what's the weight and mass of the moon? what is the relationship with the gravity acceleration?"
    )
else:
    assistant_infos = AssistantModel.create_from_ids(assistant_ids)

print(f"Using assistant id: {assistant_infos.assistant.id}")
print(f"Using thread id:    {assistant_infos.thread.id}")
print(f"Using run id:       {assistant_infos.run.id}")

# Run the runner
output = ai.await_run_completed(
    run_id= assistant_infos.run.id,
    thread_id= assistant_infos.thread.id
)
print(output)

