from helpers.execute_helper import Execute
from helpers.rag_filtering_metadata_helper import RagFilteringMetadataHelper
from langchains import langchain_rag
from models.question_analysis import QuestionAnalysis
from services.rag_service import RAGService

class RAGHybridRetrieval:
    @staticmethod    
    def rag_hybrid_retrieval(rag: RAGService, analysed_query: QuestionAnalysis, metadata, include_bm25_retrieval: bool = False, give_score: bool = True, max_retrived_count: int = 10):
        if not include_bm25_retrieval:
            rag_retrieved_chunks = RAGHybridRetrieval.rag_retrieval(rag, analysed_query, metadata, give_score, max_retrived_count)
            return rag_retrieved_chunks
        
        rag_retrieved_chunks, bm25_retrieved_chunks = Execute.run_parallel(
            (RAGHybridRetrieval.rag_retrieval, (rag, analysed_query, metadata, give_score, max_retrived_count)),
            (RAGHybridRetrieval.bm25_retrieval, (rag, analysed_query.translated_question, metadata, give_score, max_retrived_count)),
        )
        retained_chunks = RAGHybridRetrieval.hybrid_chunks_selection(rag_retrieved_chunks, bm25_retrieved_chunks, give_score, max_retrived_count)
        return retained_chunks
    
    @staticmethod    
    def rag_retrieval(rag: RAGService, analysed_query: QuestionAnalysis, filters, give_score: bool = False, max_retrieved_count: int = 10, min_score: float = None, min_retrived_count: int = None):
        retrieved_chunks = rag.rag_retrieval(analysed_query.translated_question, None, filters, give_score, max_retrieved_count, min_score, min_retrived_count)
        return retrieved_chunks
    
    @staticmethod    
    def bm25_retrieval(rag: RAGService, query: str, filters: dict, give_score: bool, k = 3):
        if filters and any(filters):
            filtered_docs = [doc for doc in rag.langchain_documents if RagFilteringMetadataHelper.filters_predicate(doc, filters)]
        else:
            filtered_docs = rag.langchain_documents

        bm25_retriever = langchain_rag.build_bm25_retriever(filtered_docs, k)#, filters
        bm25_retrieved_chunks = bm25_retriever.invoke(query)
       
        if give_score:
            score = 0.1 #todo: define the score
            return [(doc, score) for doc in bm25_retrieved_chunks]
        else:
            return bm25_retrieved_chunks
