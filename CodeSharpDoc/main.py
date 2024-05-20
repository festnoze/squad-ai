# internal import
import datetime
import uuid
from helpers.file_helper import file
from helpers.llm_helper import Llm
from helpers.txt_helper import txt
from helpers.groq_helper import GroqHelper
from langchains.langchain_adapter_type import LangChainAdapterType
from langchains.langchain_factory import LangChainFactory
from models.llm_info import LlmInfo
from services.summary_generation_service import SummaryGenerationService

# external imports
import openai
import os
from dotenv import find_dotenv, load_dotenv

print("Starting...")
load_dotenv(find_dotenv())

groq_api_key = os.getenv("GROQ_API_KEY")
openai_api_key = os.getenv("OPEN_API_KEY")
openai.api_key = openai_api_key
langsmith_api_key = os.getenv("LANGCHAIN_API_KEY")

# Setup and activate LangSmith 
from langsmith import Client
os.environ["LANGCHAIN_API_KEY"] = langsmith_api_key
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
client = Client(api_key=langsmith_api_key)

# langsmith_project = str(os.getenv("LANGCHAIN_PROJECT")) # Use the generic LangSmith project
langsmith_project = str(os.getenv("LANGCHAIN_PROJECT") + str(uuid.uuid4())) # Add a specific LangSmith projetc for this session
session = client.create_project(
   project_name=langsmith_project,
   description = f"Session of project '{os.getenv("LANGCHAIN_PROJECT")}' began on: {datetime.datetime.now()}",
)
os.environ["LANGCHAIN_PROJECT"] = langsmith_project

# Add a database to LangSmith
# dl_dataset = client.create_dataset(
#    dataset_name=dataset_name,
#    description="A deck containing flashcards on NNs and PyTorch",
#    data_type="kv",  # default
# )
# client.create_example(
#        inputs={"input": ex},
#        outputs=None,
#        dataset_id=dl_dataset.id,
#    )


# Select the LLMs to be used for first and fallbacks uses
llms_infos = []
#llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "phi3", timeout= 80, temperature = 0.5, api_key= None))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "llama2",  timeout= 200, temperature = 0.5, api_key= None))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "llama3", timeout= 200, temperature = 0.5, api_key= None))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "mistral",  timeout= 200, temperature = 0.5, api_key= None))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "mixtral",  timeout= 500, temperature = 0.5, api_key= None))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "dolphin-mixtral",  timeout= 400, temperature = 0.5, api_key= None))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "nous-hermes2", timeout= 200, temperature = 0.5, api_key= None))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "openhermes", timeout= 200, temperature = 0.5, api_key= None))

llms_infos.append(LlmInfo(type= LangChainAdapterType.Groq, model= "mixtral-8x7b-32768",  timeout= 200, temperature = 0.5, api_key= groq_api_key))
llms_infos.append(LlmInfo(type= LangChainAdapterType.Groq, model= "llama3-8b-8192",  timeout= 10, temperature = 0.5, api_key= groq_api_key))
llms_infos.append(LlmInfo(type= LangChainAdapterType.Groq, model= "llama3-70b-8192",  timeout= 20, temperature = 0.5, api_key= groq_api_key))

#llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo",  timeout= 60, temperature = 0.5, api_key= openai_api_key))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4-turbo",  timeout= 120, temperature = 0.5, api_key= openai_api_key))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4o",  timeout= 60, temperature = 0.5, api_key= openai_api_key))

# Speed test
# llms = LangChainFactory.create_llms_from_infos(llms_infos)
# res = llms[1].invoke("Hello, what is the wheter in Montpellier in june?")
# print(res)
# exit()

# Re-init. files which will be touched
file.delete_files_in_folder("inputs\\code_files_generated\\")
file.copy_folder_files_and_folders_to_folder("inputs\\code_files_saved\\", "inputs\\code_files_generated\\")
txt.activate_print = True # Activate print each step advancement

SummaryGenerationService.generate_all_summaries_for_all_csharp_files_and_save("inputs\\code_files_generated", llms_infos)
# Llm.invoke_method_mesuring_openai_tokens_consumption(
#     SummaryGenerationService.generate_all_summaries_for_all_csharp_files_and_save, 
#         "inputs\\code_files_generated", llms_infos #\\UserProfileQueryingService.cs \\IMessageService.cs
# )