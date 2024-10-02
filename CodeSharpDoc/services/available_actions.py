import json
from typing import List
#
from common_tools.helpers.file_helper import file
from common_tools.helpers.txt_helper import txt
from common_tools.models.llm_info import LlmInfo
from common_tools.RAG.rag_inference_pipeline import RagInferencePipeline
from common_tools.RAG.rag_service import RAGService
from common_tools.models.embedding_type import EmbeddingModel
#
from services.analysed_structures_handling import AnalysedStructuresHandling
from services.summary_generation_service import SummaryGenerationService

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
            AvailableActions.rag_service = RAGService(llms_infos, EmbeddingModel.OpenAI_TextEmbedding3Large)
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
                AvailableActions.generate_all_summaries(llms_infos, files_batch_size, llm_batch_size, AvailableActions.local_path)
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
                AvailableActions.rag_querying_from_console(RagInferencePipeline(RAGService(llms_infos)))
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
    def rag_querying_from_console(inference_pipeline):
        query = input("What are you looking for? ")
        additionnal_context = file.get_as_str("prompts/rag_query_code_additionnal_instructions.txt")

        while query != '':
            answer, sources = inference_pipeline(query=query, include_bm25_retieval= False, give_score= True)
            print(answer)
            if input("Do you want to see all raw retrieved documents? (y/_) ") == 'y':
                print(">>>>> Sources: <<<<<<")
                for doc in sources:
                    print("• " + doc.page_content if type(doc) != tuple else doc[0].page_content)
            print("------------------------------------")
            query = input("What next are you looking for? - (empty to quit) - ")

    @staticmethod
    def rag_querying_from_sl_chatbot(inference_pipeline, query: str, st, include_bm25_retrieval:bool = False):
        txt.print_with_spinner("Querying RAG service.")
        answer, sources = inference_pipeline.run(query=query, include_bm25_retrieval= include_bm25_retrieval, give_score= True)
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
        AvailableActions.rag_service.reset_vectorstore() # delete or empty DB first
        docs = AvailableActions.get_documents_to_vectorize_from_loaded_analysed_structures(AvailableActions.struct_desc_folder_path)
        count = AvailableActions.rag_service.build_vectorstore_and_bm25_store(docs, chunk_size=0, delete_existing=True)
        print(f"Vector store built with {count} items")

    @staticmethod
    def analyse_files_code_structures(files_batch_size: int, code_folder_path: str):
        existing_structs_analysis = AnalysedStructuresHandling.load_json_structs_from_folder_and_ask_to_replace(AvailableActions.struct_desc_folder_path)
        AnalysedStructuresHandling.analyse_code_structures_of_folder_and_save(code_folder_path, AvailableActions.struct_desc_folder_path, files_batch_size, existing_structs_analysis)

    @staticmethod
    def generate_all_summaries(llms_infos: List[LlmInfo], files_batch_size: int, llm_batch_size: int, code_folder_path: str):
        existing_structs_analysis = AnalysedStructuresHandling.load_json_structs_from_folder_and_ask_to_replace(AvailableActions.struct_desc_folder_path)
        SummaryGenerationService.generate_and_save_all_summaries_all_csharp_files_from_folder(code_folder_path, files_batch_size, llm_batch_size, existing_structs_analysis, llms_infos)


    @staticmethod
    def get_documents_to_vectorize_from_loaded_analysed_structures(struct_desc_folder_path: str) -> list[str]:
        docs: list[str] = []
        structs_str = file.get_files_contents(struct_desc_folder_path, 'json')
        for struct_str in structs_str:
            struct = json.loads(struct_str)
            summary = struct['generated_summary'] if hasattr(struct, 'generated_summary') and getattr(struct, 'generated_summary') else struct['existing_summary']
            if summary:
                doc = AvailableActions.build_document(content=summary, metadata= {'struct_type': struct['struct_type'], 'struct_name': struct['struct_name'], 'namespace': struct['namespace_name'], 'summary_kind': 'method', 'functional_type': struct['functional_type'] })
                docs.append(doc)
            for method in struct['methods']:
                summary = method['generated_summary'] if hasattr(method, 'generated_summary') and getattr(method, 'generated_summary') else method['existing_summary']
                if summary:
                    doc = AvailableActions.build_document(content=summary, metadata= {'struct_type': struct['struct_type'], 'struct_name': struct['struct_name'], 'method_name': method['method_name'], 'namespace': struct['namespace_name'], 'summary_kind': 'method', 'functional_type': struct['functional_type'] })
                    docs.append(doc)
        return docs
    
    @staticmethod
    def build_document(content: str, metadata: dict):
        return {'page_content': content, 'metadata': metadata}