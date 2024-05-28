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
openai.api_key = openai_api_key

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

llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo-0125",  timeout= 60, temperature = 0.5, api_key= openai_api_key))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo",  timeout= 60, temperature = 0.5, api_key= openai_api_key))
llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4-turbo",  timeout= 120, temperature = 0.5, api_key= openai_api_key))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4o",  timeout= 60, temperature = 1, api_key= openai_api_key))
llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4o",  timeout= 80, temperature = 0.1, api_key= openai_api_key))

# Re-init. files which will be touched
project_path = "C:/Dev/squad-ai/CodeSharpDoc"
folder_code_path = f"{project_path}/inputs/code_files_generated"
struct_desc_folder_subpath = "outputs/structures_descriptions"
struct_desc_folder_path = project_path + "/" + struct_desc_folder_subpath

file.delete_files_in_folder(folder_code_path)
file.copy_folder_files_and_folders_to_folder("inputs/code_files_saved", folder_code_path)
txt.activate_print = True # Activate print each step advancement

existing_structs_desc = SummaryGenerationService.load_struct_desc_from_folder(struct_desc_folder_path)

# Generate summaries for all C# files
if len(existing_structs_desc) > 0:
    SummaryGenerationService.generate_all_summaries_for_all_csharp_files_but_existing_and_save(folder_code_path, existing_structs_desc, llms_infos)

# Create the RAG service to search for methods by fonctionalities
llm = LangChainFactory.create_llms_from_infos(llms_infos)[0]
rag = RAGService(llm)
docs = []
structs_str = file.get_files_contents(struct_desc_folder_path, 'json')
for struct_str in structs_str:
    struct = json.loads(struct_str)
    for method in struct['methods']:
        desc = f"In {struct['struct_type']} '{struct['struct_name']}', method named: '{method['method_name']}' does: '{method['generated_summary']}'"
        docs.append(desc)
json_struct = rag.import_data(docs)
query = input("What are you looking for? ")
while query != '':
    answer, documents = rag.query(query)
    print(answer)
    for document in documents:
        print('- ' + document.page_content)
    query = input("What are you looking for? ")
print ("End program")