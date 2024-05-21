# internal import
from helpers.file_helper import file
from helpers.langsmith_helper import initialize_langsmith
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

initialize_langsmith()

# Select the LLMs to be used for first and fallbacks uses
llms_infos = []
llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "phi3", timeout= 80, temperature = 0.5, api_key= None))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "llama2",  timeout= 200, temperature = 0.5, api_key= None))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "llama3", timeout= 200, temperature = 0.5, api_key= None))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "mistral",  timeout= 200, temperature = 0.5, api_key= None))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "mixtral",  timeout= 500, temperature = 0.5, api_key= None))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "dolphin-mixtral",  timeout= 400, temperature = 0.5, api_key= None))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "nous-hermes2", timeout= 200, temperature = 0.5, api_key= None))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "openhermes", timeout= 200, temperature = 0.5, api_key= None))

#llms_infos.append(LlmInfo(type= LangChainAdapterType.Groq, model= "mixtral-8x7b-32768",  timeout= 200, temperature = 0.5, api_key= groq_api_key))
llms_infos.append(LlmInfo(type= LangChainAdapterType.Groq, model= "llama3-8b-8192",  timeout= 10, temperature = 0.5, api_key= groq_api_key))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.Groq, model= "llama3-70b-8192",  timeout= 20, temperature = 0.5, api_key= groq_api_key))

#llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo",  timeout= 60, temperature = 0.5, api_key= openai_api_key))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4-turbo",  timeout= 120, temperature = 0.5, api_key= openai_api_key))
llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4o",  timeout= 60, temperature = 0.5, api_key= openai_api_key))

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