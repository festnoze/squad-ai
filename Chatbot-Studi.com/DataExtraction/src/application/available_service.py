import asyncio
import os
import re
from textwrap import dedent
import time
from typing import AsyncGenerator
from dotenv import find_dotenv, load_dotenv
from application.ragas_service import RagasService
#
from langchain.chains.query_constructor.schema import AttributeInfo
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate
from langchain.docstore.document import Document
from data_retrieval.drupal_data_retrieval import DrupalDataRetrieval
from database_conversations.converter import ConversationConverter
from infrastructure.conversation_repository import ConversationRepository
from site_public_metadata_descriptions import MetadataDescriptionHelper
from vector_database_creation.generate_documents_and_metadata import GenerateDocumentsAndMetadata
from vector_database_creation.generate_summaries_chunks_questions_and_metadata import GenerateDocumentsSummariesChunksQuestionsAndMetadata
from web_services.request_models.user_query_asking_request_model import UserQueryAskingRequestModel
#
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.execute_helper import Execute
from common_tools.models.llm_info import LlmInfo
from common_tools.helpers.llm_helper import Llm
from common_tools.helpers.file_helper import file
from common_tools.helpers.config_helper import ConfigHelper
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.models.langchain_adapter_type import LangChainAdapterType
from common_tools.rag.rag_service import RagService
from common_tools.rag.rag_inference_pipeline.rag_pre_treatment_tasks import RAGPreTreatment
from common_tools.models.question_rewritting import QuestionRewritting, QuestionRewrittingPydantic
from common_tools.rag.rag_injection_pipeline.rag_injection_pipeline import RagInjectionPipeline
from common_tools.rag.rag_inference_pipeline.rag_inference_pipeline import RagInferencePipeline
from common_tools.rag.rag_inference_pipeline.rag_answer_generation_tasks import RAGAugmentedGeneration
from common_tools.helpers.ressource_helper import Ressource
from common_tools.models.embedding import EmbeddingModel, EmbeddingType
from common_tools.models.conversation import Conversation, Message
from common_tools.models.doc_w_summary_chunks_questions import DocWithSummaryChunksAndQuestions
from common_tools.rag.rag_inference_pipeline.end_pipeline_exception import EndPipelineException

class AvailableService:
    inference: RagInferencePipeline = None
    rag_service: RagService = None
    vector_db_type: str = None
    embedding_model: EmbeddingModel = None
    llms_infos: list[LlmInfo] = None

    def init(activate_print = True):
        load_dotenv()
        load_dotenv(dotenv_path=".rag_config.env")
        txt.activate_print = activate_print
        AvailableService.current_dir = os.getcwd()
        AvailableService.out_dir = os.path.join(AvailableService.current_dir, 'outputs')
        
        if not AvailableService.vector_db_type:
            AvailableService.vector_db_type = ConfigHelper.get_vector_db_type_from_env()
        if not AvailableService.llms_infos:
            LangChainFactory.set_openai_apikey()
            AvailableService.llms_infos = ConfigHelper.get_llms_from_env()
        if not AvailableService.rag_service:
            if not AvailableService.embedding_model:
                AvailableService.embedding_model = ConfigHelper.get_embedding_model_from_env()
            AvailableService.rag_service = RagService(
                                            llms_or_info=AvailableService.llms_infos, 
                                            embedding_model=AvailableService.embedding_model, 
                                            vector_db_type=AvailableService.vector_db_type,
                                            vector_db_name=ConfigHelper.get_vector_db_name_from_env())
            
        #TEST_LLM = AvailableService.rag_service.llm_1.invoke("quelle est la capitale de l'europe ?")

        if not AvailableService.inference:
            default_filters = {}
            metadata_descriptions_for_studi_public_site = MetadataDescriptionHelper.get_metadata_descriptions_for_studi_public_site(AvailableService.out_dir)
            AvailableService.inference = RagInferencePipeline(AvailableService.rag_service, default_filters, metadata_descriptions_for_studi_public_site, None)
            RAGAugmentedGeneration.augmented_generation_prompt = Ressource.get_rag_augmented_generation_prompt_on_studi()

    def re_init():
        AvailableService.rag_service = None
        AvailableService.inference = None
        AvailableService.init(txt.activate_print)

    def retrieve_all_data():
        drupal = DrupalDataRetrieval(AvailableService.out_dir)
        drupal.retrieve_all_data()

    def create_vector_db_from_generated_embeded_documents(out_dir):
        all_docs = GenerateDocumentsAndMetadata().load_all_docs_as_json(out_dir)
        injection_pipeline = RagInjectionPipeline(AvailableService.rag_service)
        injection_pipeline.build_vectorstore_and_bm25_store(all_docs, chunk_size= 2500, children_chunk_size= 0, vector_db_type=AvailableService.vector_db_type, collection_name= 'studi-public-full', delete_existing= True)
        AvailableService.re_init() # reload rag_service with the new vectorstore and langchain documents

    def create_summary_vector_db_from_generated_embeded_documents(out_dir):
        all_chunks = AvailableService._load_or_generate_summary_chunks_and_questions_for_docs(out_dir)
        injection_pipeline = RagInjectionPipeline(AvailableService.rag_service)
        injection_pipeline.build_vectorstore_and_bm25_store(all_chunks, chunk_size= 2500, children_chunk_size= 0, vector_db_type=AvailableService.vector_db_type, collection_name='studi-public-summarized-chunks-w-questions', delete_existing= True) #, collection_name= 'studi-summarized-questions'
        AvailableService.re_init() # reload rag_service with the new vectorstore and langchain documents

    def _load_or_generate_summary_chunks_and_questions_for_docs(out_dir):
        llm_and_fallback = [AvailableService.rag_service.llm_1, AvailableService.rag_service.llm_1, AvailableService.rag_service.llm_2, AvailableService.rag_service.llm_3]
        summary_builder = GenerateDocumentsSummariesChunksQuestionsAndMetadata()
        all_docs = summary_builder.load_or_generate_all_docs_from_summaries(out_dir, llm_and_fallback)
        return all_docs

    async def test_different_splitting_of_summarize_chunks_and_questions_creation_async(out_dir):
        summary_builder = GenerateDocumentsSummariesChunksQuestionsAndMetadata()
        trainings_docs = summary_builder._load_and_process_trainings(out_dir)

        txt.print("-"*70)
        start = time.time()
        summary_1_step = await summary_builder.create_summary_and_questions_from_docs_single_step_async([AvailableService.rag_service.llm_1, AvailableService.rag_service.llm_2], trainings_docs)
        summary_1_step_elapsed_str = txt.get_elapsed_str(time.time() - start)
        
        start = time.time()
        summary_2_steps = await summary_builder.create_summary_and_questions_from_docs_in_two_steps_async([AvailableService.rag_service.llm_1, AvailableService.rag_service.llm_2], trainings_docs)
        summary_2_steps_elapsed_str = txt.get_elapsed_str(time.time() - start)

        start = time.time()
        summary_3_steps = await summary_builder.create_summary_and_questions_from_docs_in_three_steps_async([AvailableService.rag_service.llm_1, AvailableService.rag_service.llm_2], trainings_docs)
        summary_3_steps_elapsed_str = txt.get_elapsed_str(time.time() - start)

        
        txt.print("-"*70)
        summary_1_step.display_to_terminal()
        txt.print(f"Single step summary generation took {summary_1_step_elapsed_str}")
        txt.print("-"*70)

        summary_2_steps.display_to_terminal()
        txt.print(f"Two steps summary generation took {summary_2_steps_elapsed_str}")
        txt.print("-"*70)

        summary_3_steps.display_to_terminal()
        txt.print(f"Three steps summary generation took {summary_3_steps_elapsed_str}")
        txt.print("-"*70)

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

    @staticmethod
    async def create_new_conversation_async(user_name: str = None):
        new_conv_model = Conversation(user_name)
        new_conv_entity = ConversationConverter.convert_conversation_model_to_entity(new_conv_model)
        assert await ConversationRepository().create_new_conversation_async(new_conv_entity)
        return ConversationConverter.convert_conversation_entity_to_model(new_conv_entity)

    @staticmethod
    async def rag_query_stream_async(user_query_request_model: UserQueryAskingRequestModel):
        conversation = await ConversationRepository().get_conversation_by_id_async(user_query_request_model.conversation_id)
        if not conversation: 
            raise ValueError(f"Conversation with ID {user_query_request_model.conversation_id} not found in database.")
        conversation.add_new_message("user", user_query_request_model.user_query_content)
        assert await ConversationRepository().add_message_to_conversation_async(conversation.id, conversation.last_message)
        
        # Stream the response
        all_chunks_output=[]
        response_generator = AvailableService.rag_query_retrieval_and_augmented_generation_streaming_async(conversation, False, all_chunks_output)
        async for chunk in response_generator:
            yield chunk
        
        # Add a summary of the generated answer to conversation messages and save it
        full_answer_str = Llm.get_text_from_chunks(all_chunks_output)
        summarized_response = await AvailableService.get_summarized_answer_async(full_answer_str)
        conversation.add_new_message("assistant", summarized_response)
        assert await ConversationRepository().add_message_to_conversation_async(conversation.id, conversation.last_message)
    
    @staticmethod
    async def rag_query_retrieval_and_augmented_generation_streaming_async(conversation_history:Conversation, is_stream_decoded = False, all_chunks_output: list[str] = []):
        try:
            analysed_query, retrieved_chunks = await AvailableService.rag_query_retrieval_but_augmented_generation_async(conversation_history)             
            pipeline_succeeded = True
        except EndPipelineException as ex:                        
            pipeline_succeeded = False
            pipeline_ended_response = ex.message

        if pipeline_succeeded:
            augmented_generation_streaming = AvailableService.rag_query_augmented_generation_streaming_async(analysed_query, retrieved_chunks[0], is_stream_decoded, all_chunks_output)
            async for chunk in augmented_generation_streaming:
                yield chunk
        else:
            static_text_streaming = AvailableService.write_static_text_as_stream(pipeline_ended_response)
            all_chunks_output.append(pipeline_ended_response)
            async for chunk in static_text_streaming:
                yield chunk

    async def write_static_text_as_stream(text: str, interval_btw_words: float = 0.02) -> AsyncGenerator[str, None]:
        words = text.split(" ")
        for word in words:
            yield f"{word} "
            await asyncio.sleep(interval_btw_words)

    async def rag_query_retrieval_but_augmented_generation_async(conversation_history: Conversation):
        return await AvailableService.inference.run_pipeline_dynamic_but_augmented_generation_async(conversation_history, include_bm25_retrieval= True, give_score=True, format_retrieved_docs_function = AvailableService.format_retrieved_docs_function)

    async def rag_query_augmented_generation_streaming_async(analysed_query: QuestionRewritting, retrieved_chunks: list[Document], is_stream_decoded = False, all_chunks_output: list[str] = []):
         async for chunk in RAGAugmentedGeneration.rag_augmented_answer_generation_streaming_async( 
                AvailableService.rag_service, 
                analysed_query.modified_question, 
                retrieved_chunks, 
                analysed_query, 
                is_stream_decoded,
                all_chunks_output,
                AvailableService.format_retrieved_docs_function):
            yield chunk

    async def rag_query_dynamic_pipeline_streaming_async(conversation_history: Conversation, all_chunks_output = [], decoded_stream = False):
        if conversation_history.last_message.role != 'user':
            raise ValueError("Conversation history should end with a user message")
        txt.print_with_spinner("Exécution du pipeline d'inférence ...")
        
        async for stream_chunk in AvailableService.inference.run_pipeline_dynamic_async(
            conversation_history,
            include_bm25_retrieval=True,
            give_score=True,
            format_retrieved_docs_function=AvailableService.format_retrieved_docs_function,
            all_chunks_output=all_chunks_output
        ):
            if decoded_stream:
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

        for stream_chunk in Execute.async_generator_wrapper_to_sync(
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

        sync_generator = Execute.async_generator_wrapper_to_sync(
            pipeline_method,
            conversation_history,
            True, #include_bm25_retrieval
            True, #give_score
            AvailableService.format_retrieved_docs_function, #format_retrieved_docs_function,
            None, #override_workflow_available_classes
        )
        response = Llm.get_text_from_chunks(sync_generator)
        txt.stop_spinner_replace_text("Pipeline d'inférence exectué :")
        return response
    
    #OBSOLETE: don't use this method, use async version instead
    def get_summarized_answer(text):
        summarize_rag_answer_prompt = Ressource.load_ressource_file('summarize_rag_answer_prompt.french.txt')
        promptlate = ChatPromptTemplate.from_template(summarize_rag_answer_prompt)
        chain = promptlate | AvailableService.rag_service.llm_1 | RunnablePassthrough()
        result = Execute.async_wrapper_to_sync(Llm.invoke_chain_with_input_async, 'Answer summarization', chain, text)
        return Llm.get_content(result)
    
    async def get_summarized_answer_async(text):
        summarize_rag_answer_prompt = Ressource.load_ressource_file('summarize_rag_answer_prompt.french.txt')
        promptlate = ChatPromptTemplate.from_template(summarize_rag_answer_prompt)
        chain = promptlate | AvailableService.rag_service.llm_1 | RunnablePassthrough()
        result = await Llm.invoke_chain_with_input_async('Answer summarization', chain, text)
        return Llm.get_content(result)

    def generate_ground_truth():
        #asyncio.run(RagasService.generate_ground_truth_async(AvailableService.llms_infos[0], AvailableService.rag_service.langchain_documents, 1))
        RagasService.generate_ground_truth(AvailableService.llms_infos[0], AvailableService.rag_service.langchain_documents, 1)
 
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
                drupal = DrupalDataRetrieval(AvailableService.out_dir)
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

    @staticmethod
    def create_and_fill_retrieved_data_sqlLite_database(out_dir = None):
        from database_retrieved_data.datacontext import DataContextRetrievedData
        db = DataContextRetrievedData()
        db.create_database()
        #db.add_fake_data()
        if out_dir:
            db.import_data_from_json(out_dir)