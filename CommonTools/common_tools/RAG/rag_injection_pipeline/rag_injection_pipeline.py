import re
from common_tools.rag.rag_service import RagService
import json

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

class RagInjectionPipeline:
    def __init__(self, rag: RagService):
        self.rag_service: RagService = rag

    def build_vectorstore_and_bm25_store(self, data: list, chunk_size:int = 0, children_chunk_size:int = 0, delete_existing=True)-> int:
        if not data or len(data) == 0: return 0
        self.vectorstore = self._build_vectorstore(data, chunk_size, delete_existing)
        self._build_bm25_store(data)
        return self.vectorstore._collection.count()

    def _build_vectorstore(self, documents: list, chunk_size:int = 0, delete_existing=True) -> any:
        if not documents or len(documents) == 0: raise ValueError("No documents provided")
        if not hasattr(self.rag_service, 'embedding') or not self.rag_service.embedding: raise ValueError("Embedding model must be specified to build vector store")
        if delete_existing:
            self.reset_vectorstore()
        
        langchain_documents = []
        if chunk_size > 0:
            langchain_documents = self._split_text_into_chunks(documents, chunk_size)  
            txt.print("The size of the smallest chunk is: " + str(self.get_min_size(langchain_documents)) + " words long.")
            txt.print("The size of the biggest chunk is: " + str(self.get_max_size(langchain_documents)) + " words long.")
            txt.print("The total number of chunks is: " + str(len(langchain_documents)) + " chunks.")      
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
        txt.print_with_spinner(f"Start embedding of {len(langchain_documents)} documents or chunks")
        db = self._add_documents_to_chroma(documents= langchain_documents, embedding = self.rag_service.embedding, vector_db_path= self.rag_service.vector_db_path)
        txt.stop_spinner_replace_text(f"Finished Embedding on: {len(langchain_documents)} documents")
        return db
    
    def _batch_list(self, documents, batch_size):
        for i in range(0, len(documents), batch_size):
            yield documents[i:i + batch_size]

    def _add_documents_to_chroma(self, documents, embedding, vector_db_path, max_batch_size=5000):
        for batch in self._batch_list(documents, max_batch_size):
            db = Chroma.from_documents(
                documents=batch,
                embedding=embedding,
                persist_directory=vector_db_path
            )
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
        file.write_file(json_data, self.rag_service.documents_json_filepath, file_exists_policy= FileAlreadyExistsPolicy.Override)
        
    # not in use
    def build_vectorstore_from_folder_files(self, folder_path: str, perform_chunking = True):
        txt_loader = TextLoader()
        documents = txt_loader.load(folder_path)
        return self._build_vectorstore(documents, perform_chunking)

    # @staticmethod
    # def _build_bm25_retriever(documents: list[Document], k: int = 20, metadata: dict = None) -> BM25Retriever:
    #     if not documents or len(documents) == 0: 
    #         return None
        
    #     if metadata:
    #         bm25_retriever = BM25Retriever.from_texts([doc.page_content for doc in documents], metadata)
    #     else:
    #         bm25_retriever = BM25Retriever.from_documents(documents)
    #     bm25_retriever.k = k
    #     return bm25_retriever

    def reset_vectorstore(self):
        if hasattr(self, 'vectorstore') and self.vectorstore:
            self.vectorstore.reset_collection()
            #self._delete_vectorstore_files()
    
    def get_min_size(self, documents: list[Document]) -> int:
        return min(len(re.split(r'[ .,;:!?]', doc.page_content)) for doc in documents)
    
    def get_max_size(self, documents: list[Document]) -> int:
        return max(len(re.split(r'[ .,;:!?]', doc.page_content)) for doc in documents)

    def _delete_vectorstore_files(self):
        file.delete_folder(self.rag_service.vector_db_path)
    
    def _build_document(self, content: str, metadata: dict):
        return {'page_content': content, 'metadata': metadata}
    
    def _split_text_into_chunks(self, documents: list, chunk_size: int = 2000, chunk_overlap: int = 100, max_chunk_size: int = 5461) -> list[Document]:
        all_chunks = []
        txt_splitter = CharacterTextSplitter(
            separator="\n",
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len
        )
        for document in documents:
            if not document:
                continue
            if isinstance(document, dict):
                document = Document(page_content=document.get('page_content', ''), metadata=document.get('metadata', {}))
            chunks_content = txt_splitter.split_text(document.page_content)
            chunks = [Document(page_content=chunk, metadata=document.metadata) for chunk in chunks_content]
            all_chunks.extend(chunks)

        # Ensure chunks do not exceed the maximum allowed size
        valid_chunks = []
        for chunk in all_chunks:
            if len(chunk.page_content) <= max_chunk_size*1.1:
                valid_chunks.append(Document(page_content=chunk.page_content, metadata=chunk.metadata))
            else:
                # Optionally, you can further split the chunk here if it exceeds the max size
                smaller_chunks = self._split_text_with_overlap(chunk.page_content, chunk_size, chunk_overlap)
                for small_chunk in smaller_chunks:
                    if len(small_chunk) <= max_chunk_size:
                        valid_chunks.append(Document(page_content=small_chunk, metadata=chunk.metadata))
        return valid_chunks
    
    def _split_text_with_overlap(self, content: str, chunk_size: int, chunk_overlap: int) -> list[str]:
        """
        Splits a string into chunks of specified size with overlap.
        """
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0.")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size.")

        # List to store the resulting chunks
        chunks = []
        start = 0

        while start < len(content):
            end = start + chunk_size
            chunk = content[start:end]
            chunks.append(chunk)
            
            # Move the start position forward by chunk_size minus overlap
            start += chunk_size - chunk_overlap

        return chunks
        
       