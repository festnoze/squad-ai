import asyncio
import os
import re
from textwrap import dedent
import time
from typing import AsyncGenerator, Optional
from uuid import UUID
from dotenv import find_dotenv, load_dotenv
from application.ragas_service import RagasService
#
from langchain.chains.query_constructor.schema import AttributeInfo
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate
from langchain.docstore.document import Document
from application.service_exceptions import QuotaOverloadException
from application.studi_public_website_rag_specific_config import StudiPublicWebsiteRagSpecificConfig
from data_retrieval.drupal_data_retrieval import DrupalDataRetrieval
from database_conversations.conversation_converters import ConversationConverters
from infrastructure.conversation_repository import ConversationRepository
from infrastructure.user_repository import UserRepository
from studi_public_website_metadata_descriptions import MetadataDescriptionHelper
from vector_database_creation.generate_documents_and_metadata import GenerateDocumentsAndMetadata
from vector_database_creation.generate_summaries_chunks_questions_and_metadata import GenerateDocumentsSummariesChunksQuestionsAndMetadata
from web_services.request_models.query_asking_request_model import QueryAskingRequestModel
from api.task_handler import task_handler

# Internal tools imports
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.execute_helper import Execute
from common_tools.helpers.llm_helper import Llm
from common_tools.rag.rag_service import RagService
from common_tools.rag.rag_service_factory import RagServiceFactory
from common_tools.models.question_rewritting import QuestionRewritting, QuestionRewrittingPydantic
from common_tools.rag.rag_inference_pipeline.rag_pre_treatment_tasks import RAGPreTreatment
from common_tools.rag.rag_ingestion_pipeline.rag_ingestion_pipeline import RagIngestionPipeline
from common_tools.rag.rag_ingestion_pipeline.rag_chunking import RagChunking
from common_tools.rag.rag_inference_pipeline.rag_inference_pipeline import RagInferencePipeline
from common_tools.rag.rag_inference_pipeline.rag_augmented_generation_tasks import RAGAugmentedGeneration
from common_tools.helpers.ressource_helper import Ressource
from common_tools.models.embedding_model import EmbeddingModel
from common_tools.models.embedding_type import EmbeddingType
from common_tools.models.embedding_model_factory import EmbeddingModelFactory
from common_tools.models.conversation import Conversation, Message, User
from common_tools.models.doc_w_summary_chunks_questions import DocWithSummaryChunksAndQuestions
from common_tools.models.device_info import DeviceInfo
from common_tools.rag.rag_inference_pipeline.end_pipeline_exception import EndPipelineException
from common_tools.models.vector_db_type import VectorDbType
from common_tools.helpers.env_helper import EnvHelper
from common_tools.langchains.langchain_factory import LangChainFactory

class AvailableService:
    inference: RagInferencePipeline = None
    rag_service: RagService = None
    max_conversations_by_day = 10
    max_messages_by_conversation = 10
    waiting_message = "Merci de patienter un instant ... Je cherche les informations correspondant à votre question."

    def init(activate_print = True):
        load_dotenv()
        load_dotenv(dotenv_path=".rag_config.env")
        txt.activate_print = activate_print
        AvailableService.current_dir = os.getcwd()
        AvailableService.out_dir = os.path.join(AvailableService.current_dir, 'outputs') 
        
        if not AvailableService.rag_service:
            AvailableService.rag_service = RagServiceFactory.build_from_env_config(vector_db_base_path=None)

        if not AvailableService.inference:
            default_filters = {}
            metadata_descriptions_for_studi_public_site = MetadataDescriptionHelper.get_metadata_descriptions_for_studi_public_site(AvailableService.out_dir)
            RAGAugmentedGeneration.augmented_generation_prompt = Ressource.get_rag_augmented_generation_prompt_on_studi()
            RAGPreTreatment.domain_specific_metadata_filters_validation_and_correction_async_method = StudiPublicWebsiteRagSpecificConfig.get_domain_specific_metadata_filters_validation_and_correction_async_method
            AvailableService.inference = RagInferencePipeline(rag= AvailableService.rag_service, default_filters= StudiPublicWebsiteRagSpecificConfig.get_domain_specific_default_filters(), metadata_descriptions= metadata_descriptions_for_studi_public_site, tools= None)

    def re_init():
        AvailableService.rag_service = None
        AvailableService.inference = None
        AvailableService.init(txt.activate_print)

    def retrieve_all_data():
        drupal = DrupalDataRetrieval(AvailableService.out_dir)
        drupal.retrieve_all_data()

    def create_vector_after_chunking_and_embedding_documents(out_dir, BM25_storage_in_database_sparse_vectors:bool = True):
        all_docs = GenerateDocumentsAndMetadata().load_all_docs_as_json(out_dir, write_all_lists=True)
        injection_pipeline = RagIngestionPipeline(AvailableService.rag_service)
        txt.print_with_spinner("Chunking documents...")
        documents_chunks = injection_pipeline.chunk_documents(
                                                    documents= all_docs,
                                                    chunk_size= 5000,
                                                    children_chunk_size= 0
                                                )
        txt.stop_spinner_replace_text("Documents chunked")
        txt.print_with_spinner("Inserting documents into vector database...")
        AvailableService.rag_service.vectorstore = injection_pipeline.build_vectorstore_from_chunked_docs(
                            docs_chunks= documents_chunks,
                            vector_db_type=AvailableService.rag_service.vector_db_type,
                            collection_name= AvailableService.rag_service.vector_db_name,
                            BM25_storage_in_database_sparse_vectors=BM25_storage_in_database_sparse_vectors,
                            delete_existing= True
                        )
        txt.stop_spinner_replace_text("Vector database created")
        AvailableService.re_init() # reload rag_service with the new vectorstore and langchain documents

    def create_vector_db_after_generate_chunk_and_embed_documents_summaries_and_questions(out_dir):
        llm_and_fallback = [AvailableService.rag_service.llm_1, AvailableService.rag_service.llm_1, AvailableService.rag_service.llm_2, AvailableService.rag_service.llm_3]
        generate_summaries_and_questions_services = GenerateDocumentsSummariesChunksQuestionsAndMetadata()
        all_summaries_and_questions_docs = generate_summaries_and_questions_services.load_or_generate_all_docs_from_summaries_and_questions(
                                                path= out_dir,
                                                llm_and_fallback= llm_and_fallback,
                                                separate_chunks_and_questions=False)
        
        injection_pipeline = RagIngestionPipeline(AvailableService.rag_service)
        documents_chunks = injection_pipeline.chunk_documents(
                                                    documents= all_summaries_and_questions_docs,
                                                    chunk_size= 5000,
                                                    children_chunk_size= 0
                                                )
        AvailableService.rag_service.vectorstore = injection_pipeline.build_vectorstore_from_chunked_docs(
                            docs_chunks= documents_chunks,
                            vector_db_type=AvailableService.rag_service.vector_db_type,
                            collection_name= AvailableService.rag_service.vector_db_name,
                            delete_existing= True
                        )
        AvailableService.re_init() # reload rag_service with the new vectorstore and langchain documents

    @staticmethod    
    async def test_all_llms_from_env_config_async():
        models_names = []
        # Test all LLMs including the commented ones
        llms_infos = EnvHelper.get_llms_infos_from_env_config(skip_commented_lines=False)
        llms = LangChainFactory.create_llms_from_infos(llms_infos)
        for llm in llms:
            llm_sync_test = Llm.test_llm_inference(llm)
            llm_async_test = await Llm.test_llm_inference_streaming_async(llm)
            model_name = llm.model_name if hasattr(llm, 'model_name') else llm.model if hasattr(llm, 'model') else llm.__class__.__name__

            if llm_sync_test and llm_async_test:
                models_names.append(f"SUCCESS: '{model_name}'. Sync: {llm_sync_test:2f}s. Async streaming: {llm_async_test:2f}s.")
            else:
                models_names.append(f"FAILURE: '{model_name}'. Sync: {'fails' if llm_sync_test==0.0 else 'succeed'}. Async streaming: {'fails' if llm_async_test==0.0 else 'succeed'}.")
        return models_names


    @staticmethod
    async def create_or_retrieve_user_async(user_id: Optional[UUID], user_name: str, user_device_info: DeviceInfo) -> UUID:
        user = User(
            name = user_name,
            device_info = user_device_info,
            id = user_id,
        )
        user_id = await UserRepository().create_or_update_user_async(user)
        return user_id
    
    @staticmethod
    async def create_new_conversation_async(user_id: UUID, messages: list[Message] = None) -> Conversation:
        conv_repo = ConversationRepository()
        recent_conversation_count = await conv_repo.get_recent_conversations_count_by_user_id_async(user_id)
        if recent_conversation_count > AvailableService.max_conversations_by_day: 
            raise QuotaOverloadException("You have reached the maximum number of conversations allowed per day.")
        
        new_conversation = await conv_repo.create_new_conversation_empty_async(user_id)
        new_conv = await conv_repo.get_conversation_by_id_async(new_conversation.id)
        if messages and any(messages):
            for message in messages:
                new_conv.add_new_message(message.role, message.content)
                assert await conv_repo.add_message_to_existing_conversation_async(new_conv.id, new_conv.last_message)
        return new_conv
    
    @staticmethod
    async def prepare_conversation_for_user_query_answer_async(conversation_id:UUID, user_query_content:str) -> Conversation:
        # Wait for tasks on this conversation to be finished before adding a new message
        while task_handler.is_task_ongoing(conversation_id):
            await asyncio.sleep(0.5)
        
        conv_repo = ConversationRepository()
        conversation = await conv_repo.get_conversation_by_id_async(conversation_id)
        if not conversation: raise ValueError(f"Conversation with ID {conversation_id} not found in database.")
        if len(conversation.messages) > AvailableService.max_messages_by_conversation: 
            raise QuotaOverloadException("You have reached the maximum number of messages allowed per conversation.")
        
        conversation.add_new_message("user", user_query_content)
        assert await conv_repo.add_message_to_existing_conversation_async(conversation.id, conversation.last_message)
        return conversation
        
    @staticmethod
    async def streaming_answer_to_user_query_with_RAG_async(conversation: Conversation, display_waiting_message: bool, is_stream_decoded: bool = False) -> AsyncGenerator:
        # Stream the response
        all_chunks_output=[]
        response_generator = AvailableService.rag_query_retrieval_and_augmented_generation_streaming_async(conversation, display_waiting_message, is_stream_decoded, all_chunks_output)
        async for chunk in response_generator:
            yield chunk
        
        # Add a 'background job to generate a summary of the answer, add it to conversation messages, then save it
        full_answer_str = ''.join(chunk for chunk in Llm.get_text_from_chunks(all_chunks_output))
        task_handler.add_task(
                        conversation.id, # set conversation id as task_id, so we can know if a task is ongoing for a specific conversation
                        AvailableService.add_answer_summary_to_conversation_async, 
                        conversation, 
                        full_answer_str)

    @staticmethod
    async def add_answer_summary_to_conversation_async(conversation, full_answer_str):
        summarized_response = await AvailableService.get_summarized_answer_async(full_answer_str)
        conversation.add_new_message("assistant", summarized_response)
        assert await ConversationRepository().add_message_to_existing_conversation_async(conversation.id, conversation.last_message)
    
    @staticmethod
    async def rag_query_retrieval_and_augmented_generation_streaming_async(conversation_history:Conversation, display_waiting_message = True, is_stream_decoded = False, all_chunks_output: list[str] = []):
        if display_waiting_message:
            async for chunk in Llm.write_static_text_as_stream(AvailableService.waiting_message):
                yield chunk
        try:
            analysed_query, retrieved_chunks = await AvailableService.inference.run_pipeline_dynamic_but_augmented_generation_async(conversation_history, include_bm25_retrieval= True, give_score=True, pipeline_config_file_path = 'studi_com_chatbot_rag_pipeline_default_config_wo_AG_for_streaming.yaml', format_retrieved_docs_function = AvailableService.format_retrieved_docs_function)
            pipeline_succeeded = True
        except EndPipelineException as ex:                        
            pipeline_succeeded = False
            pipeline_ended_response = ex.message

        if display_waiting_message:
            async for chunk in Llm.remove_all_previous_stream_async(True, len(AvailableService.waiting_message.split(" "))):
                yield chunk

        if pipeline_succeeded:
            augmented_generation_streaming = AvailableService.rag_query_augmented_generation_streaming_async(analysed_query, retrieved_chunks[0], is_stream_decoded, all_chunks_output)
            async for chunk in augmented_generation_streaming:
                yield chunk
        else:
            static_text_streaming = Llm.write_static_text_as_stream(pipeline_ended_response)
            all_chunks_output.append(pipeline_ended_response)
            async for chunk in static_text_streaming:
                yield chunk

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
        txt.print_with_spinner("Executing inference pipeline...")
        
        async for stream_chunk in AvailableService.inference.run_pipeline_dynamic_streaming_async(
            query=conversation_history,
            include_bm25_retrieval=True,
            give_score=True,
            pipeline_config_file_path = 'studi_com_chatbot_rag_pipeline_default_config_wo_AG_for_streaming.yaml',
            format_retrieved_docs_function=AvailableService.format_retrieved_docs_function,
            all_chunks_output=all_chunks_output
        ):
            if decoded_stream:
                yield stream_chunk.decode('utf-8').replace(Llm.new_line_for_stream_over_http, '\n')
            else:
                yield stream_chunk

        txt.stop_spinner_replace_text("Executed inference pipeline:")

    def rag_query_full_pipeline_streaming_no_async(conversation_history: Conversation, all_chunks_output = [], use_dynamic_pipeline = True, special_streaming_chars = True):
        if conversation_history.last_message.role != 'user':
            raise ValueError("Conversation history should end with a user message")
        txt.print_with_spinner("Executing inference pipeline...")
        
        pipeline_method = None
        if use_dynamic_pipeline:
            pipeline_method = AvailableService.inference.run_pipeline_dynamic_streaming_async
        else:
            pipeline_method = AvailableService.inference.run_pipeline_static_streaming_async

        for stream_chunk in Execute.async_generator_wrapper_to_sync(
            pipeline_method,
            query=conversation_history,
            include_bm25_retrieval=True,
            give_score=True,
            pipeline_config_file_path = 'studi_com_chatbot_rag_pipeline_default_config_wo_AG_for_streaming.yaml',
            format_retrieved_docs_function=AvailableService.format_retrieved_docs_function,
            all_chunks_output=all_chunks_output
        ):
            if not special_streaming_chars:
                yield stream_chunk.decode('utf-8').replace(Llm.new_line_for_stream_over_http, '\n')
            else:
                yield stream_chunk

        txt.stop_spinner_replace_text("Executed inference pipeline:")

    def rag_query_full_pipeline_no_streaming_no_async(conversation_history:Conversation, use_dynamic_pipeline = True):        
        txt.print_with_spinner("Executing inference pipeline...")
        if use_dynamic_pipeline:
            pipeline_method = AvailableService.inference.run_pipeline_dynamic_streaming_async
        else:
            pipeline_method = AvailableService.inference.run_pipeline_static_streaming_async

        all_chunks_output = []
        sync_generator = Execute.async_generator_wrapper_to_sync(
            pipeline_method,
            query=conversation_history,
            include_bm25_retrieval=True,
            give_score=True,
            pipeline_config_file_path = 'studi_com_chatbot_rag_pipeline_default_config_wo_AG_for_streaming.yaml',
            format_retrieved_docs_function=AvailableService.format_retrieved_docs_function,
            all_chunks_output=all_chunks_output
        )
        for chunk in sync_generator:
            pass
        sync_generator.close()

        response = Llm.get_text_from_chunks(all_chunks_output)
        txt.stop_spinner_replace_text("Executed inference pipeline:")
        return response
    
    async def get_summarized_answer_async(text):
        summarize_rag_answer_prompt = Ressource.load_ressource_file('summarize_rag_answer_prompt.french.txt')
        promptlate = ChatPromptTemplate.from_template(summarize_rag_answer_prompt)
        chain = promptlate | AvailableService.rag_service.llm_1 | RunnablePassthrough()
        result = await Llm.invoke_chain_with_input_async('Answer summarization', chain, text)
        return Llm.get_content(result)

    def generate_ground_truth():
        #asyncio.run(RagasService.generate_ground_truth_async(AvailableService.rag_service.llms_infos[0], AvailableService.rag_service.langchain_documents, 1))
        RagasService.generate_ground_truth(AvailableService.rag_service.llms_infos[0], AvailableService.rag_service.langchain_documents, 1)

    #todo: to delete or write to add metadata to context
    @staticmethod
    def format_retrieved_docs_function(retrieved_docs):
        if not any(retrieved_docs):
            return 'Not a single relevant information were found. Can\'t answer the question.'
        
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
