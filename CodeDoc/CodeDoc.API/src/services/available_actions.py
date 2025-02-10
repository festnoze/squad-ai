import json
from typing import Generator, List
#
from common_tools.helpers.file_helper import file
from common_tools.helpers.txt_helper import txt
from common_tools.models.llm_info import LlmInfo
from common_tools.helpers.env_helper import EnvHelper
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.rag.rag_service import RagService
from common_tools.rag.rag_service_factory import RagServiceFactory
from common_tools.models.embedding_model import EmbeddingModel
from common_tools.rag.rag_ingestion_pipeline.rag_ingestion_pipeline import RagIngestionPipeline
from common_tools.rag.rag_inference_pipeline.rag_inference_pipeline import RagInferencePipeline
from common_tools.rag.rag_ingestion_pipeline.rag_chunking import RagChunking
#
from services.analysed_structures_handling import AnalysedStructuresHandling
from services.summary_generation_service import SummaryGenerationService

class AvailableActions:
    local_path = "C:/Dev/squad-ai/CodeDoc/CodeDoc.API"
    struct_desc_folder_subpath = "outputs/structures_descriptions"
    struct_desc_folder_path = f"{local_path}/{struct_desc_folder_subpath}"
    #
    rag_service: RagService = RagServiceFactory.build_from_env_config(vector_db_base_path=None)
    inference_pipeline: RagInferencePipeline = RagInferencePipeline(rag_service)
    print("\n  -----------------------------------\n  | - Code Doc API up and running - |\n  -----------------------------------\n")
         
            
    @staticmethod
    async def rag_query_streaming_async(query: str, include_bm25_retrieval: bool = False):
        txt.print_with_spinner("Querying rag service.")
        all_chunks: list = []
        answer_generator = AvailableActions.inference_pipeline.run_pipeline_dynamic_streaming_async(
            query=query,
            include_bm25_retrieval=include_bm25_retrieval,
            give_score=True,
            format_retrieved_docs_function=AvailableActions.format_retrieved_docs_function,
            all_chunks_output=all_chunks
        )
        async for chunk in answer_generator:
            yield chunk

    @staticmethod
    async def rag_query_no_streaming_async(query: str, include_bm25_retrieval: bool = False) -> str:
        answers = await AvailableActions.inference_pipeline.run_pipeline_dynamic_no_streaming_async(
            query=query,
            include_bm25_retrieval=include_bm25_retrieval,
            give_score=True,
            format_retrieved_docs_function=AvailableActions.format_retrieved_docs_function
        )
        txt.stop_spinner_replace_text("rag retieval done")
        if not isinstance(answers, list) or not any(answers):
            return "No answer found. Don't answer the question."
        answer: str = answers[-1]
        answer = txt.remove_markdown(answer)
        return answer
        

    @staticmethod
    def format_retrieved_docs_function(retrieved_docs):
        """Formating of retrieved documents for augmented generation"""
        if not any(retrieved_docs):
            return 'not a single information were found. Don\'t answer the question.'
        context = ''
        for retrieved_doc in retrieved_docs:
            doc = retrieved_doc[0] if isinstance(retrieved_doc, tuple) else retrieved_doc
            summary = doc.page_content
            functional_type = doc.metadata.get('functional_type')
            method_name = doc.metadata.get('method_name')
            namespace = doc.metadata.get('namespace')
            struct_name = doc.metadata.get('struct_name')
            struct_type = doc.metadata.get('struct_type')

            context += f"• {summary}. In {functional_type.lower()} {struct_type.lower()}  '{struct_name}',{" method '" + method_name + "'," if method_name else ''} from namespace '{namespace}'.\n"
        return context
    
    @staticmethod
    def rebuild_vectorstore():
        docs = AvailableActions.get_documents_to_vectorize_from_loaded_analysed_structures(AvailableActions.struct_desc_folder_path)
        ingestion_pipeline = RagIngestionPipeline(AvailableActions.rag_service)
        txt.print_with_spinner("Chunking documents...")
        documents_chunks = ingestion_pipeline.chunk_documents(
                                                    documents= docs,
                                                    chunk_size= 2500,
                                                    children_chunk_size= 0
                                                )
        txt.stop_spinner_replace_text("Documents chunked")
        txt.print_with_spinner("Inserting documents into vector database...")
        AvailableActions.rag_service.vectorstore = ingestion_pipeline.build_vectorstore_from_chunked_docs(
                            docs_chunks= documents_chunks,
                            vector_db_type=AvailableActions.rag_service.vector_db_type,
                            collection_name= 'code_docs',
                            delete_existing= True
                        )
        print(f"Vector store built with {len(documents_chunks)} items")

    @staticmethod
    def analyse_files_code_structures(files_batch_size: int, code_folder_path: str):
        existing_structs_analysis = AnalysedStructuresHandling.load_all_structures_descriptions_files(AvailableActions.struct_desc_folder_path)
        AnalysedStructuresHandling.analyse_code_structures_of_folder_and_save(code_folder_path, AvailableActions.struct_desc_folder_path, files_batch_size, existing_structs_analysis)

    @staticmethod
    def generate_all_summaries(files_batch_size: int, llm_batch_size: int, code_folder_path: str):
        existing_structs_analysis = AnalysedStructuresHandling.load_all_structures_descriptions_files(AvailableActions.struct_desc_folder_path)
        SummaryGenerationService.generate_and_save_all_summaries_all_csharp_files_from_folder(code_folder_path, files_batch_size, llm_batch_size, existing_structs_analysis, AvailableActions.rag_service.llms_infos)


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
    
    
    
    
    
    # @staticmethod
    # def display_menu() -> None:
    #     print("")
    #     print("Choose one of the available actions (press number or 1st letter):")
    #     print("------------------------------------")
    #     print("1. Generate & replace summaries for all C# files in the project")
    #     print("2. Analyse code structures & summaries and save as json files")
    #     print("3. Build new vector database from analysed structures json files")
    #     print("4. Query rag service on vector database")
    #     print("5. Help: Display this menu again")
    #     print("6. Exit")

    # @staticmethod
    # def display_menu_and_actions(llms_infos: List[LlmInfo], default_first_action: int = None):
    #     # Activate print each step advancement in the console
    #     txt.activate_print = True
    #     files_batch_size = 100
    #     llm_batch_size = 100

    #     while True:
    #         if default_first_action is None:
    #             AvailableActions.display_menu()
    #             choice = input("")
    #         else:
    #             choice = str(default_first_action)
    #             default_first_action = None
            
    #         # Generate summaries for all specified C# files
    #         if choice == "1" or choice == "g":
    #             AvailableActions.generate_all_summaries(llms_infos, files_batch_size, llm_batch_size, AvailableActions.local_path)
    #             continue

    #         elif choice == "2" or choice == "a":
    #             AvailableActions.analyse_files_code_structures(files_batch_size, AvailableActions.local_path)
    #             continue

    #         # Build vector database
    #         elif choice == '3' or choice == 'b':            
    #             AvailableActions.rebuild_vectorstore()        
    #             continue

    #         # Query the rag service on methods summaries vector database
    #         elif choice == '4' or choice == 'q':            
    #             AvailableActions.rag_querying_from_console(RagInferencePipeline(AvailableActions.rag_service))
    #             continue
            
    #         elif choice == '5' or choice == 'h':
    #             AvailableActions.display_menu()
    #             continue

    #         elif choice == '6' or choice == 'e':
    #             print ("End program")
    #             break

    #         else:
    #             print("Invalid choice. Please select a valid option.")
    #             AvailableActions.display_menu()
    #             continue

    # @staticmethod
    # def rag_querying_from_console():
    #     query = input("What are you looking for? ")
    #     while query != '':
    #         answer, sources = AvailableActions.inference_pipeline(query=query, include_bm25_retieval= False, give_score= True)
    #         print(answer)
    #         if input("Do you want to see all raw retrieved documents? (y/_) ") == 'y':
    #             print(">>>>> Sources: <<<<<<")
    #             for doc in sources:
    #                 print("• " + doc.page_content if type(doc) != tuple else doc[0].page_content)
    #         print("------------------------------------")
    #         query = input("What next are you looking for? - (empty to quit) - ")

    # #OBSOLETE
    # @staticmethod
    # def rag_querying_from_sl_chatbot(inference_pipeline:RagInferencePipeline, query: str, st, include_bm25_retrieval:bool = False):
    #     txt.print_with_spinner("Querying rag service.")
        
    #     do_streaming_answer = True
    #     if do_streaming_answer:
    #         all_chunks:list = []
    #         answer_generator = inference_pipeline.run_pipeline_dynamic_streaming_sync(query=query, include_bm25_retrieval= include_bm25_retrieval, give_score= True, format_retrieved_docs_function= AvailableActions.format_retrieved_docs_function, all_chunks_output= all_chunks)
    #         st.chat_message("assistant").write_stream(answer_generator)
    #         answer = ''.join(all_chunks)
    #         answer = txt.remove_markdown(answer)
    #         st.session_state.messages.append({"role": "assistant", "content": answer})
        
    #     else:            
    #         answers = inference_pipeline.run_pipeline_dynamic_no_streaming_sync(query=query, include_bm25_retrieval= include_bm25_retrieval, give_score= True, format_retrieved_docs_function = AvailableActions.format_retrieved_docs_function)
    #         txt.stop_spinner_replace_text("rag retieval done")
    #         if not isinstance(answers, list) or not any(answers):
    #             st.session_state.messages.append({"role": "assistant", "content": "No answer found. Don't answer the question."})
    #         answer = answers[-1]
    #         answer = txt.remove_markdown(answer)
    #         st.chat_message("assistant").write(answer)
    #         st.session_state.messages.append({"role": "assistant", "content": answer})