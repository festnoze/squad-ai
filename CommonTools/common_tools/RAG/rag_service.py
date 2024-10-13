from typing import List, Optional, Union
import json

# langchain related imports
from langchain_core.language_models import BaseChatModel
from langchain_core.documents import Document
from langchain.text_splitter import CharacterTextSplitter
from langchain_community.document_loaders import TextLoader
#from langchain_community.vectorstores import FAISS
from langchain_community.retrievers import BM25Retriever
#from rank_bm25 import BM25Okapi
from langchain.retrievers import EnsembleRetriever
from langchain_chroma import Chroma
from langchain.retrievers.multi_query import MultiQueryRetriever

# common tools imports
from common_tools.helpers.ressource_helper import Ressource
from common_tools.helpers.txt_helper import txt
from common_tools.models.file_already_exists_policy import FileAlreadyExistsPolicy
from common_tools.models.llm_info import LlmInfo
from common_tools.models.question_analysis import QuestionAnalysis
from common_tools.helpers.file_helper import file
from common_tools.helpers.llm_helper import Llm
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.models.embedding_type import EmbeddingModel
from common_tools.rag.embedding_service import EmbeddingService

class RagService:
    def __init__(self, inference_llm_or_info: Optional[Union[LlmInfo, BaseChatModel]], embedding_model:EmbeddingModel=None, vector_db_and_docs_path = "./storage", documents_json_filename = "bm25_documents.json"):
        self.init_embedding(embedding_model)
        self.init_inference_llm(inference_llm_or_info) #todo: add fallbacks with specifying multiple llms or llms infos

        self.vector_db_path = vector_db_and_docs_path + '/' + self.embedding_model_name
        self.documents_json_filepath = vector_db_and_docs_path + '/' +  documents_json_filename

        self._load_bm25_retriever()
        self._load_vectorstore()

    def init_embedding(self, embedding_model:EmbeddingModel=None):
        self.embedding = EmbeddingService.get_embedding(embedding_model)
        self.embedding_model_name = embedding_model.model_name

    def init_inference_llm(self, llm_or_infos):
        if isinstance(llm_or_infos, LlmInfo) or (isinstance(llm_or_infos, list) and any(llm_or_infos) and isinstance(llm_or_infos[0], LlmInfo)):            
            self.inference_llm = LangChainFactory.create_llms_from_infos(llm_or_infos)[0]
        elif isinstance(llm_or_infos, BaseChatModel):
            self.inference_llm = llm_or_infos
        else:
            raise ValueError("Invalid llm_or_infos parameter")
    
    def semantic_vector_retrieval(self, question: str, metadata_filters: dict = None, give_score: bool = False, max_retrived_count: int = 10, min_score: float = None, min_retrived_count: int = None) -> list[Document]:
        return self._semantic_vector_retrieval(self.vectorstore, question, metadata_filters, give_score, max_retrived_count, min_score, min_retrived_count)
    
    def _semantic_vector_retrieval(self, vectorstore, question: str, metadata_filters: dict = None, give_score: bool = False, max_retrived_count: int = 10, min_score: float = None, min_retrived_count: int = None) -> List[Document]:
        #retriever_from_llm = MultiQueryRetriever.from_llm(retriever=vectorstore.as_retriever(), llm=llm)
        #results = retriever_from_llm.invoke(input==question)

        if give_score:
            results = vectorstore.similarity_search_with_score(question, k=max_retrived_count, filter=metadata_filters)
            if min_score and min_retrived_count and len(results) > min_retrived_count:
                top_results = []
                for result in results:
                    if isinstance(result, tuple) and result[1] >= min_score or len(top_results) < min_retrived_count:
                        top_results.append(result)
                results = top_results
        else:
            results = vectorstore.similarity_search(question, k=max_retrived_count, filter=metadata_filters)
        return results
            
    def _load_bm25_retriever(self, bm25_results_count: int = 1) -> tuple:
        self.langchain_documents = RagService.load_langchain_documents(self.documents_json_filepath)
        self.bm25_retriever = self._build_bm25_retriever(self.langchain_documents, bm25_results_count) #todo: useful? as metadata are retieved while querying
        return self.bm25_retriever, self.langchain_documents
    
    def load_langchain_documents(filepath:str = None) -> List[Document]:
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
        self.vectorstore = Chroma(persist_directory= self.vector_db_path, embedding_function= self.embedding)
        return self.vectorstore
    
    def build_vectorstore_and_bm25_store(self, data: list, chunk_size:int = 0, delete_existing=True)-> int:
        if not data or len(data) == 0: return 0
        self.vectorstore = self._build_vectorstore(data, chunk_size, delete_existing)
        self._build_bm25_store(data)
        return self.vectorstore._collection.count()

    def _build_vectorstore(self, documents: list, chunk_size:int = 0, delete_existing=True) -> any:
        if not documents or len(documents) == 0: raise ValueError("No documents provided")
        if not self.embedding: raise ValueError("No embedding model specified")
        if delete_existing:
            self.reset_vectorstore()
        if chunk_size > 0:
            chunks = []
            for document in documents:
                    if isinstance(document, Document):
                        chunks.extend(self._split_text_into_chunks(document.page_content, chunk_size))
                    else:
                        chunks.extend(self._split_text_into_chunks(document['page_content'], chunk_size))                
            db = Chroma.from_texts(texts= chunks, embedding = self.embedding, persist_directory= self.vector_db_path)
        else:
            if not documents or not any(documents):
                return None
            if isinstance(documents[0], Document):
                langchain_documents = documents
            else:
                langchain_documents = [
                    Document(page_content=doc["page_content"], 
                            metadata=doc["metadata"] if doc["metadata"] else '') 
                    for doc in documents
                ]
            db = Chroma.from_documents(documents= langchain_documents, embedding = self.embedding, persist_directory= self.vector_db_path)
        return db
    
    def _build_bm25_store(self, data):
        documents_dict = []
        for datum in data:
            if isinstance(datum, Document):
                documents_dict.append(self._build_document(datum.page_content, datum.metadata))
            elif isinstance(datum, dict):
                documents_dict.append(self._build_document(datum["page_content"], datum["metadata"]))
            else:
                raise ValueError("Invalid data type")
        
        json_data = json.dumps(documents_dict, ensure_ascii=False, indent=4)
        file.write_file(json_data, self.documents_json_filepath, file_exists_policy= FileAlreadyExistsPolicy.Override)
        
    # not in use
    def build_vectorstore_from_folder_files(self, folder_path: str, perform_chunking = True):
        txt_loader = TextLoader()
        documents = txt_loader.load(folder_path)
        return self._build_vectorstore(documents, perform_chunking)

    def _build_bm25_retriever(self, documents: List[Document], k: int = 20, metadata: dict = None) -> any:
        if metadata:
            bm25_retriever = BM25Retriever.from_texts([doc.page_content for doc in documents], metadata)
        else:
            bm25_retriever = BM25Retriever.from_documents(documents)
        bm25_retriever.k = k
        return bm25_retriever
        
    def reset_vectorstore(self):
        if hasattr(self, 'vectorstore') and self.vectorstore:
            self.vectorstore.reset_collection()
            #self._delete_vectorstore_files()

    def _delete_vectorstore_files(self):
        file.delete_folder(self.vector_db_path)
    
    def _build_document(self, content: str, metadata: dict):
        return {'page_content': content, 'metadata': metadata}
    
    def _split_text_into_chunks(self, text: str, chunk_size:int = 4000, chunk_overlap= 150) -> List[str]:
        txt_splitter = CharacterTextSplitter(
            separator= "\n",
            chunk_size= chunk_size,
            chunk_overlap= chunk_overlap,
            length_function= len
        )
        chunks = txt_splitter.split_text(text)
        return chunks