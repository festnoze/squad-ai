import os
from typing import List, Optional, Union
import json
from collections import defaultdict

# langchain related imports
from langchain_core.runnables import Runnable
from langchain_core.documents import Document
from langchain.text_splitter import CharacterTextSplitter
from langchain_community.document_loaders import TextLoader
from langchain_community.retrievers import BM25Retriever
#from rank_bm25 import BM25Okapi
from langchain.retrievers.multi_query import MultiQueryRetriever
from langchain.retrievers import EnsembleRetriever
from langchain_chroma import Chroma
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

# common tools imports
from common_tools.helpers.txt_helper import txt
from common_tools.models.file_already_exists_policy import FileAlreadyExistsPolicy
from common_tools.models.llm_info import LlmInfo
from common_tools.helpers.file_helper import file
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.models.embedding import EmbeddingModel

class RagService:
    def __init__(self, llms_or_info: Optional[Union[LlmInfo, Runnable, list]], embedding_model:EmbeddingModel=None, vector_db_and_docs_path:str = './storage', vector_db_type:str = 'chroma', vector_db_name:str = 'main', documents_json_filename = "bm25_documents.json"):
        self.llm_1=None
        self.llm_2=None
        self.llm_3=None
        self.init_embedding(embedding_model)
        self.init_llms(llms_or_info) #todo: add fallbacks with specifying multiple llms or llms infos
        self.vector_db_type = vector_db_type
        self.vector_db_path = os.path.join(os.path.join(os.path.abspath(vector_db_and_docs_path), self.embedding_model_name), vector_db_type)
        self.all_documents_json_file_path = os.path.abspath(os.path.join(vector_db_and_docs_path, documents_json_filename))

        self.langchain_documents = self._load_langchain_documents(self.all_documents_json_file_path)
        self.bm25_retriever = self._build_bm25_retriever(self.langchain_documents)
        self.vectorstore = self._load_vectorstore(vector_db_type, vector_db_name)

    def init_embedding(self, embedding_model:EmbeddingModel):
        self.embedding = embedding_model.create_instance()
        self.embedding_model_name = embedding_model.model_name
        
    def init_llms(self, llm_or_infos: Optional[Union[LlmInfo, Runnable, list]]):        
        if isinstance(llm_or_infos, list):
            index = 1
            for llm_or_info in llm_or_infos:
                if index == 1:
                    self.llm_1 = self._init_llm(llm_or_info)
                elif index == 2:
                    self.llm_2 = self._init_llm(llm_or_info)
                elif index == 3:
                    self.llm_3 = self._init_llm(llm_or_info)
                else:
                    raise ValueError("Only 4 llms are supported")
                index += 1
        else:
            self.llm_1 = self._init_llm(llm_or_infos)
        
        #set default llms if undefined
        if not self.llm_2: self.llm_2 = self.llm_1
        if not self.llm_3: self.llm_3 = self.llm_2
    
    def _init_llm(self, llm_or_info: Optional[Union[LlmInfo, Runnable]]):
        if isinstance(llm_or_info, LlmInfo) or (isinstance(llm_or_info, list) and any(llm_or_info) and isinstance(llm_or_info[0], LlmInfo)):            
            return LangChainFactory.create_llms_from_infos(llm_or_info)[0]
        elif isinstance(llm_or_info, Runnable):
            return llm_or_info
        else:
            raise ValueError("Invalid llm_or_infos parameter")
        
    def embed_documents(self, text:str) -> List[float]:
        return self.embedding.embed_documents(text)
    
    def semantic_vector_retrieval(self, question: str, metadata_filters: dict = None, give_score: bool = False, max_retrived_count: int = 10, min_score: float = None, min_retrived_count: int = None) -> list[Document]:
        if give_score:
            metadata_filter = metadata_filters if metadata_filters else None
            results = self.vectorstore.similarity_search_with_score(question, k=max_retrived_count, filter=metadata_filter)
            if min_score and min_retrived_count and len(results) > min_retrived_count:
                top_results = []
                for result in results:
                    if isinstance(result, tuple) and result[1] >= min_score or len(top_results) < min_retrived_count:
                        top_results.append(result)
                results = top_results
        else:
            results = self.vectorstore.similarity_search(question, k=max_retrived_count, filter=metadata_filters)
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
    
    def _load_vectorstore(self, vectorstore_type: str = 'chroma', collection_name:str = 'main') -> Optional[Union[Chroma, QdrantVectorStore]]:
        try:
            if not self.embedding: raise ValueError("As no embedding model is specified")            
            db_dir = ''
            if vectorstore_type == "chroma":
                db_dir = os.path.join(self.vector_db_path, collection_name)
            elif vectorstore_type == "qdrant":
                db_dir = self.vector_db_path
            if not file.file_exists(db_dir):
                txt.print(f'>> Vectorstore not loaded, as path: "... {db_dir[-40:]}" is not found')
                return None
            
            if vectorstore_type == "chroma":
                return Chroma(persist_directory= db_dir, embedding_function= self.embedding)
            elif vectorstore_type == "qdrant":
                qdrant_client = QdrantClient(path=db_dir)
                return QdrantVectorStore(client=qdrant_client, collection_name=collection_name, embedding=self.embedding)
        
        except Exception as e:
            txt.print(f"Error loading vectorstore: {e}")
            return None
            
    def _build_bm25_retriever(self, documents: list[Document], k: int = 20, metadata: dict = None, action_name = 'RAG BM25 retrieval') -> BM25Retriever:
        if not documents or len(documents) == 0: 
            return None
        
        if metadata:
            bm25_retriever = BM25Retriever.from_texts([doc.page_content for doc in documents], metadata)
        else:
            bm25_retriever = BM25Retriever.from_documents(documents)
        bm25_retriever.k = k
        return bm25_retriever.with_config({"run_name": f"{action_name}"})