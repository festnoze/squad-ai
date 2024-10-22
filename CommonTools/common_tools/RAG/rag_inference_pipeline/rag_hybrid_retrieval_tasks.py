from typing import Optional, Union
from common_tools.helpers.execute_helper import Execute
from common_tools.models.conversation import Conversation
from common_tools.rag.rag_filtering_metadata_helper import RagFilteringMetadataHelper
from common_tools.models.question_analysis import QuestionAnalysis
from common_tools.rag.rag_service import RagService
from common_tools.helpers.llm_helper import Llm
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.models.langchain_adapter_type import LangChainAdapterType
#
from langchain_core.documents import Document
from langchain.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import LLMChainExtractor
from langchain.retrievers.document_compressors import LLMChainFilter


class RAGHybridRetrieval:
    @staticmethod    
    def rag_hybrid_retrieval_custom(rag: RagService, query:Optional[Union[str, Conversation]], metadata:dict, include_bm25_retrieval: bool = False, give_score: bool = True, max_retrived_count: int = 20):
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
    def rag_hybrid_retrieval_langchain(rag: RagService, query:Optional[Union[str, Conversation]], metadata:dict, include_bm25_retrieval: bool = True, include_contextual_compression: bool = False, give_score: bool = True, max_retrived_count: int = 20, bm25_ratio: float = 0.2):
        vector_ratio = 1 - bm25_ratio
        # Create bm25 retriever with metadata filter
        if metadata:
            if RagFilteringMetadataHelper.does_contain_filter(metadata, 'training_info_type','url'):
                max_retrived_count = 100
            filtered_docs = [
                doc for doc in rag.langchain_documents 
                if RagFilteringMetadataHelper.filters_predicate(doc, metadata)
            ]
        else:
            filtered_docs = rag.langchain_documents

        # remove metadata filtering if no document are found
        if not any(filtered_docs):
            filtered_docs = rag.langchain_documents
            metadata = None

        bm25_retriever = rag._build_bm25_retriever(filtered_docs, k = int(max_retrived_count * bm25_ratio))
        
        # Create vectorstore retriever with metadata filter
        vector_retriever = rag.vectorstore.as_retriever(
            search_kwargs={
                "k": int(max_retrived_count * vector_ratio),
                "filter": metadata
            }
        ) 

        retrievers = [vector_retriever, bm25_retriever]        
        weights = [vector_ratio, bm25_ratio]
        ensemble_retriever = EnsembleRetriever(retrievers=retrievers, weights=weights)

        if include_contextual_compression: # todo: rather put in a separate workflow step
            filter_llm = LangChainFactory.create_llm(LangChainAdapterType.OpenAI, "gpt-4o-mini")
            _filter = LLMChainFilter.from_llm(filter_llm)
            final_retriever = ContextualCompressionRetriever(base_compressor=_filter, base_retriever=ensemble_retriever)
        else:
            final_retriever = ensemble_retriever

        question_w_history = Conversation.conversation_history_as_str(query)
        retrieved_chunks = final_retriever.invoke(question_w_history)

        # Remove 'rel_ids' from metadata: useless for augmented generation and limit token usage
        for doc in retrieved_chunks:
            doc.metadata.pop("rel_ids", None)

        return retrieved_chunks
    
    @staticmethod    
    def semantic_vector_retrieval(rag: RagService, query:Optional[Union[str, Conversation]], metadata_filters:dict, give_score: bool = False, max_retrieved_count: int = 10, min_score: float = None, min_retrived_count: int = None):
        question_w_history = Conversation.conversation_history_as_str(query)
        retrieved_chunks = rag.semantic_vector_retrieval(question_w_history, metadata_filters, give_score, max_retrieved_count, min_score, min_retrived_count)
        return retrieved_chunks
    
    @staticmethod    
    def bm25_retrieval(rag: RagService, query:Optional[Union[str, Conversation]], metadata_filters: dict, give_score: bool, k = 3):
        if metadata_filters and any(metadata_filters):
            filtered_docs = [doc for doc in rag.langchain_documents if RagFilteringMetadataHelper.filters_predicate(doc, metadata_filters)]
        else:
            filtered_docs = rag.langchain_documents

        question_w_history = Conversation.conversation_history_as_str(query)
        bm25_retriever = rag._build_bm25_retriever(filtered_docs, k) #, metadata_filters
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
    
    @staticmethod   
    def chunks_reranking_and_selection(retrieved_chunks: list[tuple[Document, float]]):
        pass    