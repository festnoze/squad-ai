from langchains import langchain_rag
from models.question_analysis import QuestionAnalysis
from services.rag_service import RAGService


class RAGAugmentedGeneration:

    @staticmethod
    def rag_augmented_answer_generation(rag: RAGService, retrieved_chunks: list, questionAnalysis: QuestionAnalysis):
        return RAGAugmentedGeneration.rag_response_generation(rag, retrieved_chunks, questionAnalysis)

    @staticmethod
    def rag_response_generation(rag: RAGService, retrieved_chunks: list, questionAnalysis: QuestionAnalysis):
        # Remove score from retrieved docs
        retrieved_chunks = [doc[0] if isinstance(doc, tuple) else doc for doc in retrieved_chunks]
        return langchain_rag.generate_response_from_retrieved_chunks(rag.llm, retrieved_chunks, questionAnalysis)
        
