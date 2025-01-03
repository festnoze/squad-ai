from typing import Optional, Union
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.execute_helper import Execute
from common_tools.models.conversation import Conversation
from common_tools.helpers.rag_filtering_metadata_helper import RagFilteringMetadataHelper
from common_tools.models.question_analysis_base import QuestionAnalysisBase
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
from langchain_core.structured_query import (
        Comparator,
        Comparison,
        Operation,
        Operator,
        StructuredQuery,
        Visitor,
)

class RAGHybridRetrieval:
    @staticmethod    
    def rag_hybrid_retrieval_custom(rag: RagService, analysed_query: QuestionAnalysisBase, metadata: dict, include_bm25_retrieval: bool = False, give_score: bool = True, max_retrived_count: int = 20):
        if not include_bm25_retrieval:
            rag_retrieved_chunks = RAGHybridRetrieval.semantic_vector_retrieval(rag, QuestionAnalysisBase.get_modified_question(analysed_query), metadata, give_score, max_retrived_count)
            return rag_retrieved_chunks
        
        rag_retrieved_chunks, bm25_retrieved_chunks = Execute.run_sync_functions_in_parallel_threads(
            (RAGHybridRetrieval.semantic_vector_retrieval, (rag, QuestionAnalysisBase.get_modified_question(analysed_query), metadata, give_score, max_retrived_count)),
            (RAGHybridRetrieval.bm25_retrieval, (rag,  QuestionAnalysisBase.get_modified_question(analysed_query), metadata, give_score, max_retrived_count)),
        )
        retained_chunks = RAGHybridRetrieval.hybrid_chunks_selection(rag_retrieved_chunks, bm25_retrieved_chunks, give_score, max_retrived_count)
        return retained_chunks
    
    @staticmethod    
    async def rag_hybrid_retrieval_langchain_async(rag: RagService, analysed_query: QuestionAnalysisBase, metadata_filters: Optional[Union[Operation, Comparison]], include_bm25_retrieval: bool = True, include_contextual_compression: bool = False, include_semantic_retrieval: bool = True, give_score: bool = True, max_retrived_count: int = 20, bm25_ratio: float = 0.2):
        if metadata_filters and not any(metadata_filters):
            metadata_filters = None
        
        if include_bm25_retrieval and include_semantic_retrieval:
            semantic_k_ratio = round(1 - bm25_ratio, 2)
        else:
            semantic_k_ratio = 1 if include_semantic_retrieval else 0
            bm25_ratio = 1 if include_bm25_retrieval else 0

        retrievers = []
        if include_semantic_retrieval:
            metadata_filters_in_specific_db_type_format = RagFilteringMetadataHelper.translate_langchain_metadata_filters_into_specified_db_type_format(metadata_filters, rag.vector_db_type)
            vector_retriever = rag.vectorstore.as_retriever(search_kwargs={'k': int(max_retrived_count * semantic_k_ratio), 'filter': metadata_filters_in_specific_db_type_format}) 
            retrievers.append(vector_retriever)
        
        if include_bm25_retrieval: 
            # Select documents matching metadata filters
            #TODO: WARNING: not generic treatment here 
            if metadata_filters:
                if RagFilteringMetadataHelper.does_contain_filter(metadata_filters, 'domaine','url'):
                    max_retrived_count = 100
                metadata_filters_chroma = RagFilteringMetadataHelper.translate_langchain_metadata_filters_into_chroma_db_format(metadata_filters)
                filtered_docs = [
                    doc for doc in rag.langchain_documents 
                    if RagFilteringMetadataHelper.metadata_filtering_predicate_ChromaDb(doc, metadata_filters_chroma)
                ]
                print(f">> docs count corresponding to metadata: {len(filtered_docs)}/{len(rag.langchain_documents)}")
            else:
                filtered_docs = rag.langchain_documents

            # Build BM25 retriever from filtered documents
            bm25_retriever = rag._build_bm25_retriever(filtered_docs, k = int(max_retrived_count * bm25_ratio))
            retrievers.append(bm25_retriever)

        if not any(retrievers): 
            raise ValueError(f"No retriever has been defined in the hybrid retrieval")

        weights = [semantic_k_ratio, bm25_ratio]
        ensemble_retriever = EnsembleRetriever(retrievers=retrievers, weights=weights)

        if include_contextual_compression: # todo: rather put in a separate workflow step
            _filter = LLMChainFilter.from_llm(rag.llm_1)
            final_retriever = ContextualCompressionRetriever(
                                    name= 'contextual compression retriever', 
                                    base_compressor=_filter, 
                                    base_retriever=ensemble_retriever)
        else:
            final_retriever = ensemble_retriever

        try:
            retrieved_chunks = await final_retriever.ainvoke(QuestionAnalysisBase.get_modified_question(analysed_query))
        except Exception as e:
            raise e
        
        # In case no docs are retrieved, re-launch the hybrid retrieval, but without metadata filters
        if metadata_filters and (not retrieved_chunks or not any(retrieved_chunks)):
            print(f">> Hybid retrieval returns no documents. Retrying without any metadata filters.")
            return await RAGHybridRetrieval.rag_hybrid_retrieval_langchain_async(rag, analysed_query, None, include_bm25_retrieval, include_contextual_compression, include_semantic_retrieval, give_score, max_retrived_count, bm25_ratio)

        # Remove 'rel_ids' from metadata: useless for augmented generation and limit token usage
        for doc in retrieved_chunks:
            doc.metadata.pop("rel_ids", None)
        return retrieved_chunks
    
    @staticmethod    
    def semantic_vector_retrieval(rag: RagService, query:Union[str, Conversation], metadata_filters:dict, give_score: bool = False, max_retrieved_count: int = 10, min_score: float = None, min_retrived_count: int = None):
        question_w_history = Conversation.conversation_history_as_str(query)
        retrieved_chunks = rag.semantic_vector_retrieval(question_w_history, metadata_filters, give_score, max_retrieved_count, min_score, min_retrived_count)
        return retrieved_chunks
    
    @staticmethod    
    def bm25_retrieval(rag: RagService, query:Union[str, Conversation], metadata_filters: dict, give_score: bool, k = 3):
        if metadata_filters and any(metadata_filters):
            filtered_docs = [doc for doc in rag.langchain_documents if RagFilteringMetadataHelper.metadata_filtering_predicate_ChromaDb(doc, metadata_filters)]
        else:
            filtered_docs = rag.langchain_documents

        question_w_history = Conversation.conversation_history_as_str(query)
        bm25_retriever = rag._build_bm25_retriever(filtered_docs, k)
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