import asyncio
from typing import Optional, Union
from common_tools.helpers.llm_helper import Llm
from common_tools.helpers.ressource_helper import Ressource
from common_tools.models.conversation import Conversation
from common_tools.models.question_analysis_base import QuestionAnalysisBase
from common_tools.rag.rag_service import RagService
from common_tools.helpers.execute_helper import Execute
from langchain_core.documents import Document
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate

class RAGAugmentedGeneration:
    augmented_generation_prompt:str = None
    @staticmethod
    def rag_augmented_answer_generation(
        rag: RagService, 
        query: Union[str, Conversation], 
        retrieved_chunks: list, 
        analysed_query: QuestionAnalysisBase, 
        format_retrieved_docs_function=None
    ):
        async def run_async():
            chunks = []
            # Collect results from the async generator
            async for chunk in RAGAugmentedGeneration.rag_augmented_answer_generation_streaming_async(
                rag, query, retrieved_chunks, analysed_query, format_retrieved_docs_function
            ):
                chunks.append(chunk)
            return ''.join(chunk.decode('utf-8') for chunk in chunks)

        #TODO: to replace with: Execute.async_generator_wrapper_to_sync

        # Ensure an event loop is available in the current thread
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # If no event loop is present, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Run the async function using the event loop
        if loop.is_running():
            # If the loop is already running, use it to run the coroutine
            return loop.run_until_complete(run_async())
        else:
            # If the loop is not running, start it and run the coroutine
            return loop.run_until_complete(run_async())

    @staticmethod
    async def rag_augmented_answer_generation_streaming_async(rag: RagService, query:Union[str, Conversation], retrieved_chunks: list, analysed_query: QuestionAnalysisBase, format_retrieved_docs_function = None):
        if retrieved_chunks and any(retrieved_chunks) and isinstance(retrieved_chunks[0], tuple): 
            retrieved_chunks = [doc[0] for doc in retrieved_chunks] # Remove scores if present

        llm_or_chain = rag.llm_1 # Select the smallest llm for the augmented generation task, as it takes lots of tokens
        if not RAGAugmentedGeneration.augmented_generation_prompt:
            RAGAugmentedGeneration.augmented_generation_prompt = Ressource.get_rag_augmented_generation_prompt_generic()
        augmented_generation_prompt = RAGAugmentedGeneration.augmented_generation_prompt

        question_w_history = Conversation.conversation_history_as_str(query)
        augmented_generation_prompt = augmented_generation_prompt.replace("{question}", question_w_history)
        
        # handle request for respond in a specific language
        additional_instructions = ''
        if hasattr(analysed_query, 'detected_language') and not analysed_query.detected_language.__contains__("english"):
            additional_instructions = Ressource.get_prefiltering_translation_instructions_prompt()
            additional_instructions = additional_instructions.replace("{target_language}", analysed_query.detected_language)
        augmented_generation_prompt = augmented_generation_prompt.replace("{additional_instructions}", additional_instructions)
        
        rag_custom_prompt = ChatPromptTemplate.from_template(augmented_generation_prompt)

        if format_retrieved_docs_function is None:
            context = retrieved_chunks
        else:
            context = format_retrieved_docs_function(retrieved_chunks)
        
        rag_chain = rag_custom_prompt | llm_or_chain | RunnablePassthrough()

        async for chunk in Llm.invoke_as_async_stream('RAG augmented generation', rag_chain, context):
            yield chunk  
