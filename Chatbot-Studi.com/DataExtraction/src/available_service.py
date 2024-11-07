import re
from textwrap import dedent
from dotenv import find_dotenv, load_dotenv
import asyncio
#
from langchain.chains.query_constructor.schema import AttributeInfo
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate
from langchain.docstore.document import Document
#from database.database import DB
from drupal_data_retireval import DrupalDataRetireval
from generate_documents_w_metadata import GenerateDocumentsWithMetadataFromFiles
#
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.execute_helper import Execute
from common_tools.models.llm_info import LlmInfo
from common_tools.helpers.llm_helper import Llm
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.models.langchain_adapter_type import LangChainAdapterType
from common_tools.rag.rag_service import RagService
from common_tools.rag.rag_inference_pipeline.rag_pre_treatment_tasks import RAGPreTreatment
from common_tools.models.question_rewritting import QuestionRewritting, QuestionRewrittingPydantic
from common_tools.rag.rag_injection_pipeline.rag_injection_pipeline import RagInjectionPipeline
from common_tools.rag.rag_inference_pipeline.rag_inference_pipeline import RagInferencePipeline
from common_tools.rag.rag_inference_pipeline.rag_answer_generation_tasks import RAGAugmentedGeneration
from common_tools.helpers.ressource_helper import Ressource
#from common_tools.rag.rag_inference_pipeline.rag_inference_pipeline_with_prefect import RagInferencePipelineWithPrefect
from common_tools.models.embedding import EmbeddingModel, EmbeddingType
from common_tools.models.conversation import Conversation
from ragas_service import RagasService
from site_public_metadata_descriptions import MetadataDescriptionHelper
import os

class AvailableService:
    inference: RagInferencePipeline = None
    rag_service: RagService = None

    def init(activate_print = True, use_prefect = False):
        AvailableService.vector_db_type = 'chroma' # 'qdrant'       
        txt.activate_print = activate_print
        LangChainFactory.set_openai_apikey() 
        AvailableService.current_dir = os.getcwd()
        AvailableService.out_dir = os.path.join(AvailableService.current_dir, 'outputs')
        if not hasattr(AvailableService, 'llms_infos') or not AvailableService.llms_infos:
            AvailableService.llms_infos = []
            #AvailableService.llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "phi3", timeout= 80, temperature = 0))

            # AvailableService.llms_infos.append(LlmInfo(type= LangChainAdapterType.Anthropic, model= "claude-3-5-haiku-20241022",  timeout= 60, temperature = 0))
            # AvailableService.llms_infos.append(LlmInfo(type= LangChainAdapterType.Anthropic, model= "claude-3-5-sonnet-20241022",  timeout= 60, temperature = 0))
            ##AvailableService.llms_infos.append(LlmInfo(type= LangChainAdapterType.Anthropic, model= "claude-3-opus-latest",  timeout= 60, temperature = 0))

            #AvailableService.llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo-0125",  timeout= 60, temperature = 0))
            #AvailableService.llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo-instruct",  timeout= 60, temperature = 0))
            AvailableService.llms_infos.append(LlmInfo(type=LangChainAdapterType.OpenAI, model="gpt-4o-mini", timeout=50, temperature=0))
            AvailableService.llms_infos.append(LlmInfo(type=LangChainAdapterType.OpenAI, model="gpt-4o", timeout=60, temperature=0))
        
        if not AvailableService.rag_service:
            AvailableService.rag_service = RagService(AvailableService.llms_infos, EmbeddingModel.OpenAI_TextEmbedding3Small, vector_db_type='qdrant') #EmbeddingModel.Ollama_AllMiniLM

        if not AvailableService.inference:
            default_filters = {} #RagFilteringMetadataHelper.get_CodeSharpDoc_default_filters()
            # if use_prefect:
            #     AvailableService.inference = RagInferencePipelineWithPrefect(AvailableService.rag_service, default_filters, None)            
            # else:
            metadata_descriptions_for_studi_public_site = MetadataDescriptionHelper.get_metadata_descriptions_for_studi_public_site(AvailableService.out_dir)
            AvailableService.inference = RagInferencePipeline(AvailableService.rag_service, default_filters, metadata_descriptions_for_studi_public_site, None)
            RAGAugmentedGeneration.augmented_generation_prompt = Ressource.get_rag_augmented_generation_prompt_on_studi()

    def re_init():
        AvailableService.rag_service = None
        AvailableService.inference = None
        AvailableService.init(txt.activate_print)

    def display_select_menu():
        while True:
            choice = input(dedent("""
                ┌──────────────────────────────┐
                │ DATA EXTRACTION - MAIN MENU  │
                └──────────────────────────────┘
                Tap the number of the selected action:  ① ② ③ ④
                1 - Retrieve data from Drupal json-api & Save as json files
                2 - Create a vector database after having generated and embedded documents
                3 - R Query: Retrieve similar documents (rag w/o Augmented Generation by LLM)
                4 - rag query: Respond with LLM augmented by similar retrieved documents
                5 - Exit
            """))
            if choice == "1":
                drupal = DrupalDataRetireval(AvailableService.out_dir)
                drupal.diplay_select_menu()
            elif choice == "2":
                AvailableService.create_vector_db_from_generated_embeded_documents(AvailableService.out_dir)
            elif choice == "3":
                AvailableService.docs_retrieval_query()
            elif choice == "4":
                AvailableService.rag_query_console()
            elif choice == "5" or choice.lower() == "e":
                print("Exiting ...")
                exit()
                #GenerateCleanedData()

    def retrieve_all_data():
        drupal = DrupalDataRetireval(AvailableService.out_dir)
        drupal.retrieve_all_data()

    def create_vector_db_from_generated_embeded_documents(out_dir):
        all_docs = GenerateDocumentsWithMetadataFromFiles().load_all_docs_as_json(out_dir)
        injection_pipeline = RagInjectionPipeline(AvailableService.rag_service)
        injection_pipeline.build_vectorstore_and_bm25_store(all_docs, chunk_size= 2500, children_chunk_size= 0, delete_existing= True, vector_db_type=AvailableService.vector_db_type)
        AvailableService.re_init() # reload rag_service with the new vectorstore and langchain documents

    def docs_retrieval_query():
        while True:
            query = input("Entrez votre question ('exit' pour quitter):\n")
            if query == "" or query == "exit":
                return None
            AvailableService.single_docs_retrieval_query(query)

    def single_docs_retrieval_query(query):        
        txt.print_with_spinner("Recherche en cours ...")
        docs = AvailableService.rag_service.semantic_vector_retrieval(query, give_score=True)
        txt.stop_spinner_replace_text(f"{len(docs)} documents trouvés")
        for doc, score in docs:
            txt.print(f"[{score:.4f}] ({doc.metadata['type']}) {doc.metadata['name']} : {doc.page_content}".strip())
        return docs
    
    def rag_query_console():        
        while True:
            query = input("Entrez votre question ('exit' pour quitter):\n")
            if query == "" or query == "exit":
                return None
            response, sources = AvailableService.inference.run(query, include_bm25_retrieval= True, give_score=True)
            txt.print(response)

    def rag_query_retrieval_but_augmented_generation(conversation_history: Conversation):
        return AvailableService.inference.run_pipeline_dynamic_but_augmented_generation(conversation_history, include_bm25_retrieval= True, give_score=True, format_retrieved_docs_function = AvailableService.format_retrieved_docs_function)

    def rag_query_augmented_generation_streaming(analysed_query: QuestionRewritting, retrieved_chunks: list[Document], decoded_stream = False, all_chunks_output: list[str] = []):
         for chunk in Execute.get_sync_generator_from_async(RAGAugmentedGeneration.rag_augmented_answer_generation_streaming_async, AvailableService.rag_service, analysed_query.modified_question, retrieved_chunks, analysed_query, AvailableService.format_retrieved_docs_function):  
            if decoded_stream:
                chunk_final = chunk.decode('utf-8').replace(Llm.new_line_for_stream_over_http, '\n')
                #if remove_markdown: chunk_final = txt.remove_markdown(chunk_final)
            else:
                chunk_final = chunk

            all_chunks_output.append(chunk_final)
            yield chunk_final

    async def rag_query_dynamic_pipeline_streaming_async(conversation_history: Conversation, all_chunks_output = [], use_dynamic_pipeline = True, special_streaming_chars = True):
        if conversation_history.last_message.role != 'user':
            raise ValueError("Conversation history should end with a user message")
        txt.print_with_spinner("Exécution du pipeline d'inférence ...")
        
        for stream_chunk in AvailableService.inference.run_pipeline_dynamic_async(
            conversation_history,
            include_bm25_retrieval=True,
            give_score=True,
            format_retrieved_docs_function=AvailableService.format_retrieved_docs_function,
            all_chunks_output=all_chunks_output
        ):
            if not special_streaming_chars:
                yield stream_chunk.decode('utf-8').replace(Llm.new_line_for_stream_over_http, '\n')
            else:
                yield stream_chunk

        txt.stop_spinner_replace_text("Pipeline d'inférence exécuté :")

    def rag_query_full_pipeline_streaming_no_async(conversation_history: Conversation, all_chunks_output = [], use_dynamic_pipeline = True, special_streaming_chars = True):
        if conversation_history.last_message.role != 'user':
            raise ValueError("Conversation history should end with a user message")
        txt.print_with_spinner("Exécution du pipeline d'inférence ...")
        
        pipeline_method = None
        if use_dynamic_pipeline:
            pipeline_method = AvailableService.inference.run_pipeline_dynamic_async
        else:
            pipeline_method = AvailableService.inference.run_pipeline_static_async

        for stream_chunk in Execute.get_sync_generator_from_async(
            pipeline_method,
            conversation_history,
            include_bm25_retrieval=True,
            give_score=True,
            format_retrieved_docs_function=AvailableService.format_retrieved_docs_function,
            all_chunks_output=all_chunks_output
        ):
            if not special_streaming_chars:
                yield stream_chunk.decode('utf-8').replace(Llm.new_line_for_stream_over_http, '\n')
            else:
                yield stream_chunk

        txt.stop_spinner_replace_text("Pipeline d'inférence exécuté :")

    def rag_query_full_pipeline_no_streaming_no_async(conversation_history:Conversation, use_dynamic_pipeline = True):        
        txt.print_with_spinner("Execution du pipeline d'inférence ...")
        if use_dynamic_pipeline:
            pipeline_method = AvailableService.inference.run_pipeline_dynamic_async
        else:
            pipeline_method = AvailableService.inference.run_pipeline_static_async

        sync_generator = Execute.get_sync_generator_from_async(
            pipeline_method,
            conversation_history,
            True, #include_bm25_retrieval
            True, #give_score
            AvailableService.format_retrieved_docs_function, #format_retrieved_docs_function,
            None, #override_workflow_available_classes
        )
        response = ''.join(chunk.decode('utf-8') for chunk in sync_generator)
        txt.stop_spinner_replace_text("Pipeline d'inférence exectué :")
        return response
    
    def get_summarized_answer(text):
        synthesize_rag_answer_prompt = Ressource.get_ressource_file_content('synthesize_rag_answer_french_prompt.txt')
        promptlate = ChatPromptTemplate.from_template(synthesize_rag_answer_prompt)
        chain = promptlate | AvailableService.rag_service.llm_1 | RunnablePassthrough()
        result = Llm.invoke_chain('Answer summarization', chain, text)
        return Llm.get_content(result)

    def generate_ground_truth():
        #asyncio.run(RagasService.generate_ground_truth_async(AvailableService.llms_infos[0], AvailableService.rag_service.langchain_documents, 1))
        RagasService.generate_ground_truth(AvailableService.llms_infos[0], AvailableService.rag_service.langchain_documents, 1)

    #todo: to delete or write to add metadata to context
    @staticmethod
    def format_retrieved_docs_function(retrieved_docs):
        if not any(retrieved_docs):
            return 'not a single information were found. Don\'t answer the question.'
        
        total_size = sum([len(re.split(r'[ .,;:!?]', doc.page_content)) for doc in retrieved_docs])
        if total_size > 15000:
            sub_list = []
            current_size = 0            
            for doc in retrieved_docs:
                doc_size = len(re.split(r'[ .,;:!?]', doc.page_content))
                if current_size + doc_size <= 15000:
                    sub_list.append(doc)
                    current_size += doc_size
                else:
                    break            
            return sub_list
        else:
            return retrieved_docs

    # def create_sqlLite_database(out_dir):
    #     db_instance = DB()
    #     db_instance.create_database()
    #     # db_instance.add_data()
    #     db_instance.import_data_from_json(out_dir)