
from typing import List
from helpers.file_helper import file
from helpers.txt_helper import txt
from langchains.langchain_factory import LangChainFactory
from models.llm_info import LlmInfo
from services.analysed_structures_handling import AnalysedStructuresHandling
from services.rag_service import RAGService
from services.summary_generation_service import SummaryGenerationService


project_path = "C:/Dev/squad-ai/CodeSharpDoc"
target_code_path = "C:/Dev/studi.api.lms.user/src"
#target_code_path = "C:/Dev/LMS/lms-api"
#target_code_path = f"{project_path}/inputs/code_files_generated"
struct_desc_folder_subpath = "outputs/structures_descriptions"
struct_desc_folder_path = f"{project_path}/{struct_desc_folder_subpath}"

def display_menu() -> None:
    print("")
    print("Choose one of the available actions (press number or 1st letter):")
    print("------------------------------------")
    print("1. Generate & replace summaries for all C# files in the project")
    print("2. Analyse code structures & summaries and save as json files")
    print("3. Build new vector database from analysed structures json files")
    print("4. Query RAG service on vector database")
    print("5. Help: Display this menu again")
    print("6. Exit")

def init_rag_service() -> RAGService:
    from services.rag_service import RAGService
    return RAGService()

def display_menu_and_actions(llms_infos: List[LlmInfo], default_first_action: int = None):
    # Activate print each step advancement in the console
    txt.activate_print = True
    files_batch_size = 100
    llm_batch_size = 100

    while True:
        if default_first_action is None:
            display_menu()
            choice = input("")
        else:
            choice = str(default_first_action)
            default_first_action = None
        
        # Generate summaries for all specified C# files
        if choice == "1" or choice == "g":
            existing_structs_analysis = AnalysedStructuresHandling.load_json_structs_from_folder_and_ask_to_replace(struct_desc_folder_path)
            SummaryGenerationService.generate_and_save_all_summaries_all_csharp_files_from_folder(target_code_path, files_batch_size, existing_structs_analysis, llms_infos)
            continue

        elif choice == "2" or choice == "a":
            existing_structs_analysis = AnalysedStructuresHandling.load_json_structs_from_folder_and_ask_to_replace(struct_desc_folder_path)
            AnalysedStructuresHandling.analyse_code_structures_of_folder_and_save(target_code_path, files_batch_size, existing_structs_analysis)
            continue

        # Build vector database
        elif choice == '3' or choice == 'b':            
            llm = LangChainFactory.create_llms_from_infos(llms_infos)[-1]
            rag = RAGService(llm)
            rag.delete_vectorstore() # delete previous DB first
            docs = rag.get_documents_to_vectorize_from_loaded_analysed_structures(struct_desc_folder_path)
            count = rag.build_vectorstore_from(docs, doChunkContent=False)
            print(f"Vector store built with {count} items")        
            continue

        # Query the RAG service on methods summaries vector database
        elif choice == '4' or choice == 'q':            
            llm = LangChainFactory.create_llms_from_infos(llms_infos)[-1]
            rag = RAGService(llm)
            count = rag.load_vectorstore(bm25_results_count= 5)
            print(f"Vector store loaded with {count} items")

            query = input("What are you looking for? ")
            additionnal_context = file.get_as_str("prompts/rag_query_code_additionnal_instructions.txt")

            while query != '':
                answer, sources = rag.query(query, additionnal_context)
                print(answer)
                if input("Do you want to see the full retieved documents? (y/_) ") == 'y':
                    print(">>>>> Sources: <<<<<<")
                    for source in sources:
                        print('- ' + source.page_content)
                print("------------------------------------")
                query = input("What next are you looking for? - (empty to quit) - ")
            display_menu()
            continue
        
        elif choice == '5' or choice == 'h':
            display_menu()
            continue
        elif choice == '6' or choice == 'e':
            print ("End program")
            break
        else:
            print("Invalid choice. Please select a valid option.")
            display_menu()
            continue