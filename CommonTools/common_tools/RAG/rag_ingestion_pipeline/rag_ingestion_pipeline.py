import os
import re
import json
import sys
import time
from typing import Union
# langchain related imports
from langchain_core.runnables import Runnable
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_chroma import Chroma
from langchain_community.query_constructors.chroma import ChromaTranslator
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from pinecone import Pinecone
from langchain_pinecone import PineconeVectorStore
from qdrant_client.http.models import Distance, VectorParams
from langchain_core.embeddings import Embeddings
import numpy as np

# common tools imports
from common_tools.helpers.txt_helper import txt
from common_tools.models.file_already_exists_policy import FileAlreadyExistsPolicy
from common_tools.helpers.file_helper import file
from common_tools.rag.rag_ingestion_pipeline.sparse_vector_embedding import SparseVectorEmbedding
from common_tools.rag.rag_service import RagService
from common_tools.models.vector_db_type import VectorDbType
from common_tools.helpers.batch_helper import BatchHelper
from common_tools.rag.rag_ingestion_pipeline.rag_chunking import RagChunking
import uuid

class RagIngestionPipeline:
    def __init__(self, rag: RagService):
        self.rag_service: RagService = rag

    def chunk_documents(self, documents: list, chunk_size:int = 1000, children_chunk_size= 0) -> list[Document]:
        """Chunks the provided documents into small pieces"""
        documents_chunks:list[Document] = []
        if chunk_size > 0:
            documents_chunks = RagChunking.split_text_into_chunks(documents, chunk_size, chunk_size/10 if chunk_size != 0 else 0)  
            txt.print("Size of the smallest chunk is: " + str(self._get_doc_min_size(documents_chunks)) + " words long.")
            txt.print("Size of the biggest chunk is: " + str(self._get_doc_max_size(documents_chunks)) + " words long.")
            txt.print("Total count: " + str(len(documents_chunks)) + " chunks.")      
        else:
            if not documents or not any(documents):
                return None
            if isinstance(documents[0], Document):
                documents_chunks = documents
            else:
                documents_chunks = [
                    Document(page_content=doc["page_content"], 
                            metadata=doc["metadata"] if doc["metadata"] else '') 
                    for doc in documents
                ]
        return documents_chunks

    def build_vectorstore_from_chunked_docs(self, docs_chunks: list, vector_db_type: VectorDbType = None, collection_name:str = 'main', BM25_storage_in_database_sparse_vectors=True, delete_existing=True) -> any:
        """
        Builds the vector store from chunked documents.
        Args:
            chunks (list): List of document chunks to be embedded and stored.
            vector_db_type (VectorDbType, optional): Type of vector database to use. Defaults to 'chroma'.
            collection_name (str, optional): Name of the collection in the vector database. Defaults to 'main'.
            BM25_storage_in_database_sparse_vectors (bool, optional): 
                - If True: BM25 storage in database as sparse vectors.
                - If False: storage in json file of full docs/chunks.
            delete_existing (bool, optional): Flag to determine if existing vector store should be deleted before building a new one. Defaults to True.
        Returns:
            any: The database object after storing the document chunks.
        """
        if not vector_db_type: vector_db_type = VectorDbType('chroma')
        if not docs_chunks or len(docs_chunks) == 0: raise ValueError("No documents provided")
        if not hasattr(self.rag_service, 'embedding') or not self.rag_service.embedding: raise ValueError("Embedding model must be specified to build vector store")
        if delete_existing:
            self._reset_vectorstore(self.rag_service)        
        
        txt.print_with_spinner(f"Start embedding of {len(docs_chunks)} chunks of documents...")
        
        # Create Json file containing raw docs for BM25 retrieval
        if not BM25_storage_in_database_sparse_vectors:
            self._build_bm25_store_as_raw_json_file(docs_chunks)

        # Embed and store the chunks as dense vectors in database + create a Json file containing raw BM25 docs
        if not BM25_storage_in_database_sparse_vectors:
            if vector_db_type == VectorDbType.Qdrant:
                db = self._embed_and_store_documents_chunks_as_dense_vectors_into_qdrant_db(documents= docs_chunks, embedding = self.rag_service.embedding, vector_db_path= self.rag_service.vector_db_path, collection_name=collection_name)
            elif vector_db_type == VectorDbType.ChromaDB:
                db = self._embed_and_store_documents_chunks_as_dense_vectors_into_chroma_db(documents= docs_chunks, embedding = self.rag_service.embedding, vector_db_path= self.rag_service.vector_db_path, collection_name=collection_name)
            elif vector_db_type == VectorDbType.Pinecone:
                db = self._embed_and_store_documents_chunks_as_dense_vectors_into_pinecone_db(documents= docs_chunks)
            else:
                raise ValueError("Invalid vector db type: " + vector_db_type.value)
           
        
        # Embed and store the chunks as dense & sparse vectors in vector database - allow to perform both semantic and BM25 retrieving from the same database
        if BM25_storage_in_database_sparse_vectors:
            if vector_db_type == VectorDbType.Qdrant:
                raise NotImplementedError("Sparse vectors for BM25 are not implemented for Qdrant.")
            elif vector_db_type == VectorDbType.ChromaDB:
                raise NotImplementedError("Sparse vectors for BM25 are not implemented for Chroma.")
            elif vector_db_type == VectorDbType.Pinecone:
                db = self._embed_and_store_documents_as_dense_and_sparse_vectors_into_pinecone_db(
                                documents= docs_chunks,
                                pinecone_index= self.rag_service.vectorstore._index,
                                embedding_model= self.rag_service.embedding)
        txt.stop_spinner_replace_text(f"Done. {len(docs_chunks)} documents' chunks embedded sucessfully!")
        return db

    def _embed_and_store_documents_chunks_as_dense_vectors_into_chroma_db(self, documents:list[Document], embedding, vector_db_path:str, collection_name:str = 'main', batch_size:int = 2000):
        for batch in BatchHelper.batch_split_by_count(documents, batch_size):
            db = Chroma.from_documents(
                documents=batch,
                embedding=embedding,
                persist_directory= os.path.join(vector_db_path, collection_name)
            )
        return db
    
    def _embed_and_store_documents_chunks_as_dense_vectors_into_qdrant_db(self, documents:list[Document], embedding:Embeddings, vector_db_path: str = '', collection_name:str = 'main', batch_size:int = 2000) -> QdrantVectorStore:
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
        for batch in BatchHelper.batch_split_by_count(documents, batch_size):
            db.add_documents(batch)
        return db
     
    def _embed_and_store_documents_chunks_as_dense_vectors_into_pinecone_db(self, documents:list[Document], batch_size:int = 2000) -> PineconeVectorStore:
        for batch in BatchHelper.batch_split_by_count(documents, batch_size):
            self.rag_service.vectorstore.add_documents(batch)
        return self.rag_service.vectorstore
    
    def _embed_and_store_documents_as_dense_and_sparse_vectors_into_pinecone_db(self, documents: list[Document], pinecone_index, embedding_model: Embeddings, batch_mega_bytes: int = 1):
        """
        Embeds documents with BM25 (sparse) and dense embeddings and stores them in Pinecone.
        
        Args:
            documents (list[Document]): List of LangChain Document objects.
            pinecone_index: Pinecone index instance.
            bm25_embedding_model: Model or method to compute BM25 sparse vectors.
            dense_embedding_model: Model or method to compute dense embeddings.
        """
        all_entries = self._embed_as_both_sparse_and_dense_vectors(documents, embedding_model, True, 2000)

        # Insert the joined embeddings into Pinecone vector database
        insertion_batches = BatchHelper.batch_split_by_size_in_kilo_bytes(all_entries, batch_mega_bytes * 1024)
        for i, batch_entries in enumerate(insertion_batches):
            txt.replace_text_continue_spinner(f"Batch {i+1}/{len(insertion_batches)}: {len(batch_entries)} documents uploaded to Pinecone...")
            pinecone_index.upsert(batch_entries)

        txt.replace_text_continue_spinner(f"All documents sucessfully uploaded to Pinecone...")
        return Pinecone(index=pinecone_index, embedding=embedding_model)

    def _embed_as_both_sparse_and_dense_vectors(self, documents:list[Document], embedding_model:Embeddings, load_embeddings_if_already_exists:bool = True, batch_embedding_size:int = 2000, wait_seconds_btw_batches:float = None) -> list[dict]:
        joined_embeddings_filepath = os.path.join(self.rag_service.vector_db_base_path, "joined_sparse_and_dense_embeddings_adapted_to_pinecone.json")
        if load_embeddings_if_already_exists and file.exists(joined_embeddings_filepath):
            return file.get_as_json(joined_embeddings_filepath)
        
        sparse_vector_embedder = SparseVectorEmbedding()
        SparseVectorEmbedding.set_path(self.rag_service.vector_db_base_path)
        all_docs_contents = [doc.page_content for doc in documents]
            
        # Step 1: Compute Sparse Vectors (BM25)
        bm25_vectors = sparse_vector_embedder.embed_documents_as_sparse_vectors_for_BM25_initial(all_docs_contents)
        SparseVectorEmbedding.save_vectorizer()

        # Step 2: Compute Dense Vectors
        dense_vectors_filepath = os.path.join(self.rag_service.vector_db_base_path, "dense_vectors.npy")
        dense_vectors = []
        if not file.exists(dense_vectors_filepath):
            for documents_batch in BatchHelper.batch_split_by_count(all_docs_contents, batch_embedding_size):
                dense_vectors_for_batch = embedding_model.embed_documents(documents_batch)
                dense_vectors.extend(dense_vectors_for_batch)
                if wait_seconds_btw_batches: 
                    time.sleep(wait_seconds_btw_batches)
            dense_vectors_array = np.array(dense_vectors)
            np.save(dense_vectors_filepath, dense_vectors_array)
        else:       
            dense_vectors_array = np.load(dense_vectors_filepath)
            dense_vectors = dense_vectors_array.tolist()        

        # Step 3: Prepare joined sparse and dense embedding dict (compatible with Pinecone Entries) - also inc. metadata from the original documents
        all_entries = []
        for doc, bm25_vector, dense_vector in zip(documents, bm25_vectors, dense_vectors):            
            bm25_sparse_dict = sparse_vector_embedder.csr_to_pinecone_dict(bm25_vector) # Convert CSR matrix to Pinecone dictionary
            doc.metadata["parent_id"] = doc.metadata.get("id", "")  # Add the original id into metadata if exists

            # Combine sparse and dense vectors as two fields of a single entry (correspond to Pinecone's structure)
            entry = {
                    "id": str(uuid.uuid4()),  # Ensure unique IDs
                    "values": dense_vector,  # Pinecone handles dense vectors in the 'values' field
                    "sparse_values": bm25_sparse_dict,  # BM25 sparse vector for hybrid search
                    "metadata": doc.metadata  # Add metadata for filtering
                }
            all_entries.append(entry)
            
        # Save joined embeddings as file 
        all_entries_json = json.dumps(all_entries, ensure_ascii=False, indent=4)
        file.write_file(all_entries_json, joined_embeddings_filepath, FileAlreadyExistsPolicy.Override)
        return all_entries

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

    def _reset_vectorstore(self, rag: RagService = None):
        if rag.vectorstore:
            if rag.vector_db_type != VectorDbType.Pinecone:
                rag.vectorstore.reset_collection()
            elif rag.vector_db_type == VectorDbType.Pinecone:
                try:
                    if rag.vectorstore and rag.vectorstore._index:
                        rag.vectorstore._index.delete(delete_all=True)
                        Pinecone.delete_index(rag.vector_db_name)
                except Exception as e:
                    txt.print(f"Deleting pinecone index '{rag.vectorstore._index._config.host}' vectors fails with: {e}")

    def _get_doc_min_size(self, documents: list[Document]) -> int:
        return min(len(re.split(r'[ .,;:!?]', doc.page_content)) for doc in documents)
    
    def _get_doc_max_size(self, documents: list[Document]) -> int:
        return max(len(re.split(r'[ .,;:!?]', doc.page_content)) for doc in documents)

    def _delete_vectorstore_files(self):
        file.delete_folder(self.rag_service.vector_db_path)
    
    def _build_document(self, content: str, metadata: dict):
        return {'page_content': content, 'metadata': metadata}