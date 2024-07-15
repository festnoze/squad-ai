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

print("Starting...")
load_dotenv(find_dotenv())

groq_api_key = os.getenv("GROQ_API_KEY")
openai_api_key = os.getenv("OPEN_API_KEY")
google_api_key = os.getenv("GOOGLE_API_KEY")
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
#openai.api_key = openai_api_key

langsmith = Langsmith()
#langsmith.delete_all_project_sessions()
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
    print("1. Generate summaries for all C# files in the project")
    print("2. Build vector database from analysed structs json files")
    print("3. Query the RAG service")
    print("4. Help: Display this menu again")
    print("5. Exit")

project_path = "C:/Dev/squad-ai/CodeSharpDoc"
generated_code_path = f"{project_path}/inputs/code_files_generated"
origin_code_path = f"{project_path}/inputs/code_files_saved"
struct_desc_folder_subpath = "outputs/structures_descriptions"
struct_desc_folder_path = project_path + "/" + struct_desc_folder_subpath
llm = LangChainFactory.create_llms_from_infos(llms_infos)[-1]
rag = RAGService(llm)

print_menu()

while True:
    choice = input("")
    
    # Generate summaries for all specified C# files
    if (choice == "1" or choice == "g"):
        # Re-initialize files which will be touched
        file.delete_files_in_folder(generated_code_path)
        file.copy_folder_files_and_folders_to_folder(origin_code_path, generated_code_path)
        txt.activate_print = True # Activate print each step advancement in the console

        existing_structs_desc, json_files = SummaryGenerationService.load_json_structs_desc_from_folder(struct_desc_folder_path)
        if existing_structs_desc:
            print(f"{len(existing_structs_desc)} structures descriptions already exist. We will keep those structures descriptions...")
            update_choice = input("... unless you want to Regenerate them? (r/_) ")
            if update_choice == 'r':
                for json_file in json_files:
                    file.delete_file(json_file)
                existing_structs_desc = []
        SummaryGenerationService.generate_and_save_all_summaries_all_csharp_files_from_folder(generated_code_path, existing_structs_desc, llms_infos)
        continue

    # Build vector database
    elif choice == '2' or choice == 'b':
        rag.delete_vectorstore() # delete previous DB first
        docs = rag.load_structures_summaries(struct_desc_folder_path)
        count = rag.build_vectorstore_from(docs)
        print(f"Vector store built with {count} items")        
        continue

    # Query the RAG service on methods summaries vector database
    elif choice == '3' or choice == 'q':
        count = rag.load_vectorstore()
        print(f"Vector store loaded with {count} items")

        query = input("What are you looking for? ")
        additionnal_context = file.get_as_str("inputs/rag_query_code_additionnal_instructions.txt")

        while query != '':
            answer, documents = rag.query(query, additionnal_context)
            print(answer)
            #if input("Do you want to see the sources? (y/_) ") == 'y':
            print("Sources:")
            for document in documents:
                print('- ' + document.page_content)
            print("------------------------------------")
            query = input("What are you looking for next (empty to quit)? ")
        print_menu()
        continue
    
    elif choice == '4' or choice == 'h':
        print_menu()
        continue
    elif choice == '5' or choice == 'e':
        print ("End program")
        break
    else:
        print("Invalid choice. Please select a valid option.")
        print_menu()
        continue