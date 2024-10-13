from typing import Optional, Union
from common_tools.helpers.llm_helper import Llm
from common_tools.helpers.ressource_helper import Ressource
from common_tools.models.conversation import Conversation
from common_tools.models.question_analysis import QuestionAnalysis
from common_tools.rag.rag_service import RagService
from langchain_core.language_models import BaseChatModel
from langchain_core.documents import Document
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate

class RAGAugmentedGeneration:

    @staticmethod
    def rag_augmented_answer_generation(rag: RagService, query:Optional[Union[str, Conversation]], retrieved_chunks: list, analysed_query: QuestionAnalysis, format_retrieved_docs_function = None):
        return RAGAugmentedGeneration.rag_response_generation(rag, query, retrieved_chunks, analysed_query, format_retrieved_docs_function)

    @staticmethod
    def rag_response_generation(rag: RagService, query:Optional[Union[str, Conversation]], retrieved_chunks: list, questionAnalysis: QuestionAnalysis, format_retrieved_docs_function = None):
        if retrieved_chunks and any(retrieved_chunks) and isinstance(retrieved_chunks[0], tuple) : retrieved_chunks = [doc[0] for doc in retrieved_chunks] # Remove scores if present

        return RAGAugmentedGeneration.generate_augmented_response_from_retrieved_chunks(rag.inference_llm, query, retrieved_chunks, questionAnalysis, format_retrieved_docs_function)

    @staticmethod
    def generate_augmented_response_from_retrieved_chunks(llm: BaseChatModel, query:Optional[Union[str, Conversation]], retrieved_docs: list[Document], analysed_query: QuestionAnalysis, format_retrieved_docs_function = None) -> str:
        retrieval_prompt = Ressource.get_rag_augmented_generation_query_prompt()
        question_w_history = Conversation.get_conv_history_as_str(query)
        retrieval_prompt = retrieval_prompt.replace("{question}", question_w_history)
        additional_instructions = ''
        if not analysed_query.detected_language.__contains__("english"):
            additional_instructions = Ressource.get_prefiltering_translation_instructions_prompt()
            additional_instructions = additional_instructions.replace("{target_language}", analysed_query.detected_language)
        retrieval_prompt = retrieval_prompt.replace("{additional_instructions}", additional_instructions)
        rag_custom_prompt = ChatPromptTemplate.from_template(retrieval_prompt)

        if format_retrieved_docs_function is None:
            context = retrieved_docs
        else:
            context = format_retrieved_docs_function(retrieved_docs)
        
        rag_chain = rag_custom_prompt | llm | RunnablePassthrough()
        answer = rag_chain.invoke(input= context)

        return Llm.get_content(answer)   
