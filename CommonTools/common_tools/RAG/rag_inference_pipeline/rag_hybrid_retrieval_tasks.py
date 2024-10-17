from typing import Optional, Union
from common_tools.helpers.execute_helper import Execute
from common_tools.models.conversation import Conversation
from common_tools.rag.rag_filtering_metadata_helper import RagFilteringMetadataHelper
from common_tools.models.question_analysis import QuestionAnalysis
from common_tools.rag.rag_service import RagService
#
from langchain_core.documents import Document
from langchain.retrievers import BM25Retriever, EnsembleRetriever

class RAGHybridRetrieval:
    @staticmethod    
    def rag_static_hybrid_retrieval(rag: RagService, query:Optional[Union[str, Conversation]], metadata:dict, include_bm25_retrieval: bool = False, give_score: bool = True, max_retrived_count: int = 10):
        if not include_bm25_retrieval:
            rag_retrieved_chunks = RAGHybridRetrieval.semantic_vector_retrieval(rag, query, metadata, give_score, max_retrived_count)
            return rag_retrieved_chunks
        
        rag_retrieved_chunks, bm25_retrieved_chunks = Execute.run_parallel(
            (RAGHybridRetrieval.semantic_vector_retrieval, (rag, query, metadata, give_score, max_retrived_count)),
            (RAGHybridRetrieval.bm25_retrieval, (rag, query, metadata, give_score, max_retrived_count)),
        )
        retained_chunks = RAGHybridRetrieval.hybrid_chunks_selection(rag_retrieved_chunks, bm25_retrieved_chunks, give_score, max_retrived_count)
        return retained_chunks
    
    @staticmethod    
    def rag_langchain_hybrid_retrieval(rag: RagService, query:Optional[Union[str, Conversation]], metadata:dict, include_bm25_retrieval: bool = True, give_score: bool = True, max_retrived_count: int = 10, bm25_ratio: float = 0.2):
        vector_ratio = 1 - bm25_ratio

        rag.bm25_retriever.k =  int(max_retrived_count * bm25_ratio)
        ensemble_retriever = EnsembleRetriever(retrievers=[
            rag.vectorstore.as_retriever(search_kwargs={"k": int(max_retrived_count * vector_ratio)}), 
            rag.bm25_retriever],
            weights=[1 - bm25_ratio, bm25_ratio])
        question_w_history = Conversation.get_conv_history_as_str(query)
        retrieved_chunks = ensemble_retriever.invoke(question_w_history)
        return retrieved_chunks
    
    @staticmethod    
    def semantic_vector_retrieval(rag: RagService, query:Optional[Union[str, Conversation]], metadata_filters:dict, give_score: bool = False, max_retrieved_count: int = 10, min_score: float = None, min_retrived_count: int = None):
        question_w_history = Conversation.get_conv_history_as_str(query)
        retrieved_chunks = rag.semantic_vector_retrieval(question_w_history, metadata_filters, give_score, max_retrieved_count, min_score, min_retrived_count)
        return retrieved_chunks
    
    @staticmethod    
    def bm25_retrieval(rag: RagService, query:Optional[Union[str, Conversation]], metadata_filters: dict, give_score: bool, k = 3):
        if metadata_filters and any(metadata_filters):
            filtered_docs = [doc for doc in rag.langchain_documents if RagFilteringMetadataHelper.filters_predicate(doc, metadata_filters)]
        else:
            filtered_docs = rag.langchain_documents

        question_w_history = Conversation.get_conv_history_as_str(query)
        bm25_retriever = rag._build_bm25_retriever(filtered_docs, k) #, filters
        bm25_retrieved_chunks = bm25_retriever.invoke(question_w_history)
       
        if give_score:
            score = 0.1 #todo: define the score
            return [(doc, score) for doc in bm25_retrieved_chunks]
        else:
            return bm25_retrieved_chunks

    @staticmethod   
    def hybrid_chunks_selection(rag_retrieved_chunks: list[tuple[Document, float]], bm25_retrieved_chunks: list[tuple[Document, float]] = None, give_score: bool = False, max_retrived_count: int = None):
        if not bm25_retrieved_chunks or not any(bm25_retrieved_chunks):
            return rag_retrieved_chunks
        
        rag_retrieved_chunks.extend([(chunk, 0) for chunk in bm25_retrieved_chunks] if give_score else bm25_retrieved_chunks)
        
        if max_retrived_count:
            if give_score:
                rag_retrieved_chunks = sorted(rag_retrieved_chunks, key=lambda x: x[1], reverse=True)
            rag_retrieved_chunks = rag_retrieved_chunks[:max_retrived_count]

        return rag_retrieved_chunks
    