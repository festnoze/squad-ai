from common_tools.models.question_analysis import QuestionAnalysis
from common_tools.RAG.rag_service import RAGService

class RAGAugmentedGeneration:

    @staticmethod
    def rag_augmented_answer_generation(rag: RAGService, retrieved_chunks: list, questionAnalysis: QuestionAnalysis, give_score: bool = True):
        return RAGAugmentedGeneration.rag_response_generation(rag, retrieved_chunks, questionAnalysis, give_score)

    @staticmethod
    def rag_response_generation(rag: RAGService, retrieved_chunks: list, questionAnalysis: QuestionAnalysis, give_score: bool = True):
        # Remove score from retrieved docs
        retrieved_chunks = [doc[0] if give_score else doc for doc in retrieved_chunks]
        return rag.generate_augmented_response_from_retrieved_chunks(rag.inference_llm, retrieved_chunks, questionAnalysis)
        
