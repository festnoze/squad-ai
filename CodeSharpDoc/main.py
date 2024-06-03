# internal import
import json
from helpers.file_helper import file
from helpers.langsmith_helper import Langsmith
from helpers.llm_helper import Llm
from helpers.txt_helper import txt
from helpers.groq_helper import GroqHelper
from langchains.langchain_adapter_type import LangChainAdapterType
from langchains.langchain_factory import LangChainFactory
from models.llm_info import LlmInfo
from services.rag_service import RAGService
from services.summary_generation_service import SummaryGenerationService

# external imports
import openai
import os
from dotenv import find_dotenv, load_dotenv

print("Starting...")
load_dotenv(find_dotenv())

groq_api_key = os.getenv("GROQ_API_KEY")
openai_api_key = os.getenv("OPEN_API_KEY")
google_api_key = os.getenv("GOOGLE_API_KEY")
#openai.api_key = openai_api_key

langsmith = Langsmith()
langsmith.delete_all_project_sessions()
langsmith.create_project()

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

#llms_infos.append(LlmInfo(type= LangChainAdapterType.Groq, model= "mixtral-8x7b-32768",  timeout= 20, temperature = 0.5, api_key= groq_api_key))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.Groq, model= "llama3-8b-8192",  timeout= 10, temperature = 0.5, api_key= groq_api_key))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.Groq, model= "llama3-70b-8192",  timeout= 20, temperature = 0.5, api_key= groq_api_key))

#llms_infos.append(LlmInfo(type= LangChainAdapterType.Google, model= "gemini-pro",  timeout= 60, temperature = 0.5, api_key= google_api_key))

llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo-0125",  timeout= 60, temperature = 0.5, api_key= openai_api_key))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo",  timeout= 60, temperature = 0.5, api_key= openai_api_key))
llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4-turbo",  timeout= 120, temperature = 0.5, api_key= openai_api_key))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4o",  timeout= 60, temperature = 1, api_key= openai_api_key))
llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4o",  timeout= 80, temperature = 0.1, api_key= openai_api_key))


# Re-initialize files which will be touched
project_path = "C:/Dev/squad-ai/CodeSharpDoc"
generated_code_path = f"{project_path}/inputs/code_files_generated"
origin_code_path = f"{project_path}/inputs/code_files_saved"
struct_desc_folder_subpath = "outputs/structures_descriptions"
struct_desc_folder_path = project_path + "/" + struct_desc_folder_subpath

file.delete_files_in_folder(generated_code_path)
file.copy_folder_files_and_folders_to_folder(origin_code_path, generated_code_path)
txt.activate_print = True # Activate print each step advancement in the console

existing_structs_desc = SummaryGenerationService.load_struct_desc_from_folder(struct_desc_folder_path)

# Generate summaries for all new C# files
SummaryGenerationService.generate_and_save_all_summaries_all_csharp_files_from_folder(generated_code_path, existing_structs_desc, llms_infos)

# Create the RAG service on methods summaries vector database
llm = LangChainFactory.create_llms_from_infos(llms_infos)[-1]
rag = RAGService(llm)
if input("Do you to rebuild vectorstore from analysed structs? (y/_) ") == 'y':
    docs = rag.load_structures_summaries(struct_desc_folder_path)
    count = rag.build_vectorstore_from(docs)
    print(f"Vector store built with {count} items")
else:
    count = rag.load_vectorstore()
    print(f"Vector store loaded with {count} items")

query = input("What are you looking for? ")
additionnal_context = file.get_as_str("inputs/rag_query_code_additionnal_instructions.txt")

while query != '':
    answer, documents = rag.query(query, additionnal_context)
    print(answer)
    if input("Do you want to see the sources? (y/_) ") == 'y':
        for document in documents:
            print('- ' + document.page_content)
    query = input("What are you looking for? ")
print ("End program")