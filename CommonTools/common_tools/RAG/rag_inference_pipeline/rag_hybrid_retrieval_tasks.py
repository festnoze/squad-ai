from common_tools.helpers.execute_helper import Execute
from common_tools.RAG.rag_filtering_metadata_helper import RagFilteringMetadataHelper
from common_tools.models.question_analysis import QuestionAnalysis
from common_tools.RAG.rag_service import RAGService
#
from langchain_core.documents import Document

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
    def rag_retrieval(rag: RAGService, analysed_query: QuestionAnalysis, metadata_filters, give_score: bool = False, max_retrieved_count: int = 10, min_score: float = None, min_retrived_count: int = None):
        retrieved_chunks = rag.retrieve(analysed_query.translated_question, None, metadata_filters, give_score, max_retrieved_count, min_score, min_retrived_count)
        return retrieved_chunks
    
    @staticmethod    
    def bm25_retrieval(rag: RAGService, query: str, filters: dict, give_score: bool, k = 3):
        if filters and any(filters):
            filtered_docs = [doc for doc in rag.langchain_documents if RagFilteringMetadataHelper.filters_predicate(doc, filters)]
        else:
            filtered_docs = rag.langchain_documents

        bm25_retriever = rag._build_bm25_retriever(filtered_docs, k)#, filters
        bm25_retrieved_chunks = bm25_retriever.invoke(query)
       
        if give_score:
            score = 0.1 #todo: define the score
            return [(doc, score) for doc in bm25_retrieved_chunks]
        else:
            return bm25_retrieved_chunks

    @staticmethod   
    def hybrid_chunks_selection(rag_retrieved_chunks: list[Document], bm25_retrieved_chunks: list[Document] = None, give_score: bool = False, max_retrived_count: int = None):
        if not bm25_retrieved_chunks or not any(bm25_retrieved_chunks):
            return rag_retrieved_chunks
        
        rag_retrieved_chunks.extend([(chunk, 0) for chunk in bm25_retrieved_chunks] if give_score else bm25_retrieved_chunks)
        
        if max_retrived_count:
            if give_score:
                rag_retrieved_chunks = sorted(rag_retrieved_chunks, key=lambda x: x[1], reverse=True)
            rag_retrieved_chunks = rag_retrieved_chunks[:max_retrived_count]

        return rag_retrieved_chunks
    