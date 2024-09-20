
from typing import List
from helpers.file_helper import file
from helpers.txt_helper import txt
from langchains.langchain_factory import LangChainFactory
from models.llm_info import LlmInfo
from rag_inference_pipeline import RagInferencePipeline
from services.analysed_structures_handling import AnalysedStructuresHandling
from services.rag_service import RAGService
from services.summary_generation_service import SummaryGenerationService
import langchains.langchain_rag as langchain_rag


class AvailableActions:

    local_path = "C:/Dev/squad-ai/CodeSharpDoc"
    # target_code_path = "C:/Dev/studi.api.lms.user/src"
    # target_code_path = "C:/Dev/LMS/lms-api"
    # target_code_path = f"{project_path}/inputs/code_files_generated"
    struct_desc_folder_subpath = "outputs/structures_descriptions"
    struct_desc_folder_path = f"{local_path}/{struct_desc_folder_subpath}"
    rag_service: RAGService = None

    @staticmethod
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

    def init_rag_service(llms_infos) -> RAGService:
        if not AvailableActions.rag_service:
            AvailableActions.rag_service = RAGService(llms_infos)
        return AvailableActions.rag_service

    @staticmethod
    def display_menu_and_actions(llms_infos: List[LlmInfo], default_first_action: int = None):
        # Activate print each step advancement in the console
        txt.activate_print = True
        files_batch_size = 100
        llm_batch_size = 100

        while True:
            if default_first_action is None:
                AvailableActions.display_menu()
                choice = input("")
            else:
                choice = str(default_first_action)
                default_first_action = None
            
            # Generate summaries for all specified C# files
            if choice == "1" or choice == "g":
                AvailableActions.generate_all_summaries(llms_infos, files_batch_size, llm_batch_size, AvailableActions.local_path, struct_desc_folder_path)
                continue

            elif choice == "2" or choice == "a":
                AvailableActions.analyse_files_code_structures(files_batch_size, AvailableActions.local_path)
                continue

            # Build vector database
            elif choice == '3' or choice == 'b':            
                AvailableActions.rebuild_vectorstore(llms_infos)        
                continue

            # Query the RAG service on methods summaries vector database
            elif choice == '4' or choice == 'q':            
                AvailableActions.rag_querying_from_console(RAGService(llms_infos))
                continue
            
            elif choice == '5' or choice == 'h':
                AvailableActions.display_menu()
                continue

            elif choice == '6' or choice == 'e':
                print ("End program")
                break

            else:
                print("Invalid choice. Please select a valid option.")
                AvailableActions.display_menu()
                continue

    @staticmethod
    def rag_querying_from_console(rag: RAGService):
        query = input("What are you looking for? ")
        additionnal_context = file.get_as_str("prompts/rag_query_code_additionnal_instructions.txt")

        while query != '':
            answer, sources = RagInferencePipeline(rag, query, additionnal_context, include_bm25_retieval= False, give_score= True)
            print(answer)
            if input("Do you want to see all raw retrieved documents? (y/_) ") == 'y':
                print(">>>>> Sources: <<<<<<")
                for doc in sources:
                    print("• " + doc.page_content if type(doc) != tuple else doc[0].page_content)
            print("------------------------------------")
            query = input("What next are you looking for? - (empty to quit) - ")

    @staticmethod
    def rag_querying_from_sl_chatbot(inference_pipeline: RagInferencePipeline, query: str, st):
        txt.print_with_spinner("Querying RAG service.")
        answer, sources = inference_pipeline.run(query=query, include_bm25_retrieval= False, give_score= True)
        txt.stop_spinner_replace_text("RAG retieval done")
        answer = txt.remove_markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.chat_message("assistant").write(answer)

        #sources = "Sources : \n" + langchain_rag.get_str_from_rag_retrieved_docs (sources)
        #st.session_state.messages.append({"role": "assistant", "content": txt.remove_markdown(sources)})
        #st.text(sources)

    @staticmethod
    def rebuild_vectorstore(llms_infos: List[LlmInfo]):
        AvailableActions.init_rag_service(llms_infos)
        AvailableActions.rag_service.empty_vectorstore() # delete or empty DB first
        docs = AvailableActions.rag_service.get_documents_to_vectorize_from_loaded_analysed_structures(AvailableActions.struct_desc_folder_path)
        count = AvailableActions.rag_service.build_vectorstore_from(docs, doChunkContent=False)
        print(f"Vector store built with {count} items")

    @staticmethod
    def analyse_files_code_structures(files_batch_size: int, code_folder_path: str):
        existing_structs_analysis = AnalysedStructuresHandling.load_json_structs_from_folder_and_ask_to_replace(AvailableActions.struct_desc_folder_path)
        AnalysedStructuresHandling.analyse_code_structures_of_folder_and_save(code_folder_path, AvailableActions.struct_desc_folder_path, files_batch_size, existing_structs_analysis)

    @staticmethod
    def generate_all_summaries(llms_infos: List[LlmInfo], files_batch_size: int, llm_batch_size: int, code_folder_path: str):
        existing_structs_analysis = AnalysedStructuresHandling.load_json_structs_from_folder_and_ask_to_replace(AvailableActions.struct_desc_folder_path)
        SummaryGenerationService.generate_and_save_all_summaries_all_csharp_files_from_folder(code_folder_path, files_batch_size, llm_batch_size, existing_structs_analysis, llms_infos)