# internal import
import json
from helpers.file_helper import file
from langchains.langsmith_client import Langsmith
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

load_dotenv(find_dotenv())

groq_api_key = os.getenv("GROQ_API_KEY")
openai_api_key = os.getenv("OPEN_API_KEY")
google_api_key = os.getenv("GOOGLE_API_KEY")
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
#openai.api_key = openai_api_key

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

#llms_infos.append(LlmInfo(type= LangChainAdapterType.Anthropic, model= "claude-2",  timeout= 60, temperature = 0.5, api_key= anthropic_api_key))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.Anthropic, model= "claude-3-opus-20240229",  timeout= 60, temperature = 0.5, api_key= anthropic_api_key))

llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo-0125",  timeout= 60, temperature = 0.5, api_key= openai_api_key))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo",  timeout= 60, temperature = 0.5, api_key= openai_api_key))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4-turbo",  timeout= 120, temperature = 0.5, api_key= openai_api_key))
#llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4o",  timeout= 60, temperature = 1, api_key= openai_api_key))
llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4o",  timeout= 80, temperature = 0.1, api_key= openai_api_key))

def print_menu() -> None:
    print("")
    print("Choose one of the available actions (press number or 1st letter):")
    print("------------------------------------")
    print("1. Generate & replace summaries for all C# files in the project")
    print("2. Analyse code structures & summaries and save structs json files")
    print("3. Build new vector database from analysed structures json files")
    print("4. Query RAG service on vector database")
    print("5. Help: Display this menu again")
    print("6. Exit")

print("Starting...")
langsmith = Langsmith()
langsmith.delete_all_project_sessions()
langsmith.create_project()

project_path = "C:/Dev/squad-ai/CodeSharpDoc"
target_code_path = "C:/Dev/studi.api.lms.user/src"
#target_code_path = "C:/Dev/LMS/lms-api"
#target_code_path = f"{project_path}/inputs/code_files_generated"
struct_desc_folder_subpath = "outputs/structures_descriptions"
struct_desc_folder_path = f"{project_path}/{struct_desc_folder_subpath}"
#
llm = LangChainFactory.create_llms_from_infos(llms_infos)[-1]
rag = RAGService(llm)

txt.activate_print = True # Activate print each step advancement in the console

print_menu()
while True:
    choice = input("")
    
    # Generate summaries for all specified C# files
    if choice == "1" or choice == "g":
        existing_structs_analysis = SummaryGenerationService.load_json_structs_from_folder_and_ask_to_replace(struct_desc_folder_path)
        SummaryGenerationService.generate_and_save_all_summaries_all_csharp_files_from_folder(target_code_path, existing_structs_analysis, llms_infos)
        continue

    elif choice == "2" or choice == "a":
        existing_structs_analysis = SummaryGenerationService.load_json_structs_from_folder_and_ask_to_replace(struct_desc_folder_path)
        SummaryGenerationService.save_structures_analysis_code_files_from_folder(target_code_path, existing_structs_analysis, llms_infos)
        continue

    # Build vector database
    elif choice == '3' or choice == 'b':
        rag.delete_vectorstore() # delete previous DB first
        docs = rag.load_structures_summaries(struct_desc_folder_path)
        count = rag.build_vectorstore_from(docs)
        print(f"Vector store built with {count} items")        
        continue

    # Query the RAG service on methods summaries vector database
    elif choice == '4' or choice == 'q':
        count = rag.load_vectorstore(bm25_results_count= 5)
        print(f"Vector store loaded with {count} items")

        query = input("What are you looking for? ")
        additionnal_context = file.get_as_str("inputs/rag_query_code_additionnal_instructions.txt")

        while query != '':
            answer, sources = rag.query(query, additionnal_context)
            print(answer)
            #if input("Do you want to see the sources? (y/_) ") == 'y':
            print(">>>>> Sources: <<<<<<")
            for source in sources:
                print('- ' + source.page_content)
            print("------------------------------------")
            query = input("What next are you looking for? - empty to quit. ")
        print_menu()
        continue
    
    elif choice == '5' or choice == 'h':
        print_menu()
        continue
    elif choice == '6' or choice == 'e':
        print ("End program")
        break
    else:
        print("Invalid choice. Please select a valid option.")
        print_menu()
        continue