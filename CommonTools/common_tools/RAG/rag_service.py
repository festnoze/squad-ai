import os
from typing import List, Optional, Union
import json
from collections import defaultdict

# langchain related imports
from langchain_core.runnables import Runnable
from langchain_core.documents import Document
from langchain.text_splitter import CharacterTextSplitter
from langchain_community.document_loaders import TextLoader
#from langchain_community.vectorstores import FAISS
from langchain_community.retrievers import BM25Retriever
from langchain_community.query_constructors.chroma import ChromaTranslator
#from rank_bm25 import BM25Okapi
from langchain.retrievers.multi_query import MultiQueryRetriever
from langchain.retrievers import EnsembleRetriever
from langchain_chroma import Chroma
from langchain.chains.query_constructor.base import AttributeInfo

# common tools imports
from common_tools.helpers.txt_helper import txt
from common_tools.models.file_already_exists_policy import FileAlreadyExistsPolicy
from common_tools.models.llm_info import LlmInfo
from common_tools.helpers.file_helper import file
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.models.embedding import EmbeddingModel
from langchain.retrievers.self_query.base import SelfQueryRetriever
from langchain.chains.query_constructor.base import StructuredQueryOutputParser, get_query_constructor_prompt

class RagService:
    def __init__(self, inference_llm_or_info: Optional[Union[LlmInfo, Runnable]], embedding_model:EmbeddingModel=None, vector_db_and_docs_path = "./storage", documents_json_filename = "bm25_documents.json"):
        self.init_embedding(embedding_model)
        self.init_inference_llm(inference_llm_or_info) #todo: add fallbacks with specifying multiple llms or llms infos

        self.vector_db_path = vector_db_and_docs_path + '/' + self.embedding_model_name
        self.documents_json_filepath = vector_db_and_docs_path + '/' +  documents_json_filename

        self.langchain_documents = self._load_langchain_documents(self.documents_json_filepath)
        self.bm25_retriever = self._build_bm25_retriever(self.langchain_documents)
        self.vectorstore = self._load_vectorstore()

    def init_embedding(self, embedding_model:EmbeddingModel):
        self.embedding = embedding_model.create_instance()
        self.embedding_model_name = embedding_model.model_name

    def init_inference_llm(self, llm_or_infos: Optional[Union[LlmInfo, Runnable]]):
        if isinstance(llm_or_infos, LlmInfo) or (isinstance(llm_or_infos, list) and any(llm_or_infos) and isinstance(llm_or_infos[0], LlmInfo)):            
            self.llm = LangChainFactory.create_llms_from_infos(llm_or_infos)[0]
        elif isinstance(llm_or_infos, Runnable):
            self.llm = llm_or_infos
        else:
            raise ValueError("Invalid llm_or_infos parameter")
    
    def semantic_vector_retrieval(self, question: str, metadata_filters: dict = None, give_score: bool = False, max_retrived_count: int = 10, min_score: float = None, min_retrived_count: int = None) -> list[Document]:
        return self._semantic_vector_retrieval(self.vectorstore, question, metadata_filters, give_score, max_retrived_count, min_score, min_retrived_count)
    
    def _semantic_vector_retrieval(self, vectorstore, question: str, metadata_filters: dict = None, give_score: bool = False, max_retrived_count: int = 10, min_score: float = None, min_retrived_count: int = None) -> List[Document]:
        #retriever_from_llm = MultiQueryRetriever.from_llm(retriever=vectorstore.as_retriever(), llm=llm)
        #results = retriever_from_llm.invoke(input==question)
        if give_score:
            metadata_filter = metadata_filters if metadata_filters else None
            results = vectorstore.similarity_search_with_score(question, k=max_retrived_count, filter=metadata_filter)
            if min_score and min_retrived_count and len(results) > min_retrived_count:
                top_results = []
                for result in results:
                    if isinstance(result, tuple) and result[1] >= min_score or len(top_results) < min_retrived_count:
                        top_results.append(result)
                results = top_results
        else:
            results = vectorstore.similarity_search(question, k=max_retrived_count, filter=metadata_filters)
        return results
    
    def _load_langchain_documents(self, filepath:str = None) -> List[Document]:
        if not file.file_exists(filepath):
            txt.print(">>> No file found with langchain documents. Please provide a valid file path.")
            return None
                        
        json_as_str = file.read_file(filepath)
        json_data = json.loads(json_as_str)
        docs = [
            Document(page_content=doc["page_content"], metadata=doc["metadata"]) 
            for doc in json_data ]
        return docs
    
    def _load_vectorstore(self):
        if not self.embedding: raise ValueError("No embedding model specified")
        abs_path = os.path.abspath(self.vector_db_path)
        vectorstore = Chroma(persist_directory= abs_path, embedding_function= self.embedding)
        return vectorstore
    
    def _build_bm25_retriever(self, documents: list[Document], k: int = 20, metadata: dict = None) -> BM25Retriever:
        if not documents or len(documents) == 0: 
            return None
        
        if metadata:
            bm25_retriever = BM25Retriever.from_texts([doc.page_content for doc in documents], metadata)
        else:
            bm25_retriever = BM25Retriever.from_documents(documents)
        bm25_retriever.k = k
        return bm25_retriever
        
    #todo: move to inference pipeline?
    def build_self_querying_retriever_langchain(self, metadata_description: list[AttributeInfo] = None, get_query_constructor:bool = True) -> tuple :
        document_description = "Description of the document"
        if not metadata_description:
            metadata_description = RagService.generate_metadata_info_from_docs(self.langchain_documents)

        if get_query_constructor:
            query_constructor = self.build_query_with_extracted_metadata(metadata_description)
            self_querying_retriever = SelfQueryRetriever(
                query_constructor=query_constructor,
                vectorstore=self.vectorstore,
                structured_query_translator=ChromaTranslator(),
            )
            return self_querying_retriever, query_constructor
        else:
            self_querying_retriever = SelfQueryRetriever.from_llm(
                self.llm,
                self.vectorstore,
                document_description,
                metadata_description,
            )
            return self_querying_retriever, None

    def build_query_with_extracted_metadata(self, metadata_description: list[AttributeInfo] = None):
        document_description = "Description of the document"
        prompt = get_query_constructor_prompt(
            document_description,
            metadata_description,
        )
        output_parser = StructuredQueryOutputParser.from_components()
        query_constructor = prompt | self.llm | output_parser
        return query_constructor
        
    @staticmethod
    def generate_metadata_info_from_docs(documents: list[Document], max_values: int = 10, metadata_keys_description:dict = None) -> list[AttributeInfo]:
        metadata_field_info = []
        value_counts = defaultdict(list)

        for doc in documents:
            for key, value in doc.metadata.items():
                if value not in value_counts[key]:
                    value_counts[key].append(value)

        for key, values in value_counts.items():
            description = f"'{key}' metadata"
            if metadata_keys_description and key in metadata_keys_description:
                description += f" (indicate: {metadata_keys_description[key]})"
            value_type = type(values[0]).__name__
            if len(values) <= max_values:
                values_str = ', '.join([f"'{value}'" for value in values])
                description += f". One value in: [{values_str}]"
            
            metadata_field_info.append(AttributeInfo(name=key, description=description, type=value_type))

        return metadata_field_info
