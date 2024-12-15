import os
import re
import json

# langchain related imports
from langchain_core.runnables import Runnable
from langchain_core.documents import Document
from langchain.text_splitter import CharacterTextSplitter, RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader
from langchain_core.embeddings import Embeddings
#from langchain_community.vectorstores import FAISS
from langchain_community.retrievers import BM25Retriever
#from rank_bm25 import BM25Okapi
from langchain.retrievers.multi_query import MultiQueryRetriever
from langchain.retrievers import EnsembleRetriever
from langchain_chroma import Chroma
from langchain_community.query_constructors.chroma import ChromaTranslator
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from langchain_pinecone import PineconeVectorStore
from qdrant_client.http.models import Distance, VectorParams

# common tools imports
from common_tools.helpers.txt_helper import txt
from common_tools.models.file_already_exists_policy import FileAlreadyExistsPolicy
from common_tools.helpers.file_helper import file
from common_tools.rag.rag_injection_pipeline.sparse_vector_embedding import SparseVectorEmbedding
from common_tools.rag.rag_service import RagService
from common_tools.models.vector_db_type import VectorDbType

class RagInjectionPipeline:
    def __init__(self, rag: RagService):
        self.rag_service: RagService = rag

    def build_vectorstore_and_bm25_store(self, documents: list, chunk_size:int = 2000, children_chunk_size:int = 0, vector_db_type: VectorDbType= None, collection_name:str = 'main', delete_existing=True)-> int:
        self.vectorstore = self._build_vectorstore(documents, chunk_size, vector_db_type, collection_name, delete_existing)
        self._build_bm25_store_as_raw_json_file(documents)

    def _build_vectorstore(self, documents: list, chunk_size:int = 1000, vector_db_type: VectorDbType = None, collection_name:str = 'main', delete_existing=True) -> any:
        if not vector_db_type: vector_db_type = VectorDbType('chroma')
        if not documents or len(documents) == 0: raise ValueError("No documents provided")
        if not hasattr(self.rag_service, 'embedding') or not self.rag_service.embedding: raise ValueError("Embedding model must be specified to build vector store")
        if delete_existing:
            self.reset_vectorstore()
        
        langchain_documents = []
        if chunk_size > 0:
            langchain_documents = self._split_text_into_chunks(documents, chunk_size, chunk_size/10 if chunk_size != 0 else 0)  
            txt.print("Size of the smallest chunk is: " + str(self.get_min_size(langchain_documents)) + " words long.")
            txt.print("Size of the biggest chunk is: " + str(self.get_max_size(langchain_documents)) + " words long.")
            txt.print("Total count: " + str(len(langchain_documents)) + " chunks.")      
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
        txt.print_with_spinner(f"Start embedding of {len(langchain_documents)} chunks of documents...")
        if vector_db_type == VectorDbType.Qdrant:
            db = self._add_documents_to_qdrant(documents= langchain_documents, embedding = self.rag_service.embedding, vector_db_path= self.rag_service.vector_db_path, collection_name=collection_name)
        elif vector_db_type == VectorDbType.ChromaDB:
            db = self._add_documents_to_chroma(documents= langchain_documents, embedding = self.rag_service.embedding, vector_db_path= self.rag_service.vector_db_path, collection_name=collection_name)
        elif vector_db_type == VectorDbType.Pinecone:
            db = self._add_documents_to_pinecone(documents= langchain_documents, embedding = self.rag_service.embedding, vector_db_path= self.rag_service.vector_db_path, collection_name=collection_name)
        else:
            raise ValueError("Invalid vector db type: " + vector_db_type.value)
        txt.stop_spinner_replace_text(f"Done. {len(langchain_documents)} documents' chunks embedded sucessfully!")
        return db
    
    def _batch_list(self, documents, batch_size):
        for i in range(0, len(documents), batch_size):
            yield documents[i:i + batch_size]

    def _add_documents_to_chroma(self, documents:list[Document], embedding, vector_db_path:str, collection_name:str = 'main', max_batch_size:int=5000):
        for batch in self._batch_list(documents, max_batch_size):
            db = Chroma.from_documents(
                documents=batch,
                embedding=embedding,
                persist_directory= os.path.join(vector_db_path, collection_name)
            )
        return db
    
    def _add_documents_to_qdrant(self, documents:list[Document], embedding:Embeddings, vector_db_path: str = '', collection_name:str = 'main') -> QdrantVectorStore:
        vector_size = len(embedding.embed_query("test"))  # Determine the vector size
        qdrant_client = QdrantClient(path=vector_db_path)
        qdrant_client.recreate_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
        )
        db = QdrantVectorStore(
            client= qdrant_client,
            collection_name= collection_name,
            embedding= embedding
        )
        db.add_documents(documents)
        return db
     
    def _add_documents_to_pinecone(self, documents:list[Document], embedding:Embeddings, vector_db_path: str = '', collection_name:str = 'main') -> PineconeVectorStore:
        self.rag_service.vectorstore.add_documents(documents)
        return self.rag_service.vectorstore

    def _build_bm25_store_as_raw_json_file(self, documents:list):
        documents_dict = []
        for document in documents:
            if isinstance(document, Document):
                documents_dict.append(self._build_document(document.page_content, document.metadata))
            elif isinstance(document, dict):
                documents_dict.append(self._build_document(document["page_content"], document["metadata"]))
            else:
                raise ValueError("Invalid data type")
        
        json_data = json.dumps(documents_dict, ensure_ascii=False, indent=4)
        file.write_file(json_data, self.rag_service.all_documents_json_file_path, file_exists_policy= FileAlreadyExistsPolicy.Override)
        
    # not in use
    def _build_bm25_store_as_sparse_vectors(self, folder_path: str, perform_chunking = True):
        txt_loader = TextLoader()
        documents = txt_loader.load(folder_path)
        return self._build_vectorstore(documents, perform_chunking)

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
        txt_splitter = self._get_text_splitter(chunk_size, chunk_overlap)
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
            if len(chunk.page_content.split(' ')) <= max_chunk_size*1.15:
                valid_chunks.append(Document(page_content=chunk.page_content, metadata=chunk.metadata))
            else:
                # Optionally, you can further split the chunk here if it exceeds the max size
                smaller_chunks = self._split_text_with_overlap(chunk.page_content, chunk_size, chunk_overlap)
                for small_chunk in smaller_chunks:
                    if len(small_chunk) <= max_chunk_size:
                        valid_chunks.append(Document(page_content=small_chunk, metadata=chunk.metadata))
        return valid_chunks

    def _get_text_splitter(self, chunk_size, chunk_overlap):
        txt_splitter = RecursiveCharacterTextSplitter(
            separators=["\n\n", "\r\n", "\n", " ", ""],
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len
        )        
        return txt_splitter
    
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
    
    #TODO: to finish
    def embed_and_store_documents_in_pinecone(self, documents: list[Document], pinecone_index, bm25_embedding_model):
        """
        Embeds documents with BM25 (sparse) and dense embeddings and stores them in Pinecone.
        
        Args:
            documents (list[Document]): List of LangChain Document objects.
            pinecone_index: Pinecone index instance.
            bm25_embedding_model: Model or method to compute BM25 sparse vectors.
            dense_embedding_model: Model or method to compute dense embeddings.
        """
        # Step 1: Compute Sparse Vectors (BM25)
        bm25_vectors = SparseVectorEmbedding().embed_documents_as_sparse_vectors_for_BM25_initial(documents, bm25_embedding_model)

        # Step 2: Compute Dense Vectors
        dense_vectors = self.rag_service.embedding.embed_documents([doc.page_content for doc in documents])

        # Step 3: Prepare Pinecone Entries
        entries = []
        for doc, bm25_vector, dense_vector in zip(documents, bm25_vectors, dense_vectors):
            # Combine sparse and dense vectors into a single item
            entry = {
                "id": doc.metadata.get("id", f"doc-{hash(doc.page_content)}"),  # Ensure unique IDs
                "values": dense_vector,  # Pinecone handles dense vectors in the 'values' field
                "sparse_values": bm25_vector,  # BM25 sparse vector for hybrid search
                "metadata": doc.metadata  # Add metadata for filtering
            }
            entries.append(entry)

        # Step 4: Upsert to Pinecone
        pinecone_index.upsert(entries)
        #return Pinecone(index=pinecone_index, embedding=dense_embedding_model)
        
       