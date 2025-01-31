import os
import time
from typing import List, Optional, Union
import json
from collections import defaultdict

# langchain related imports
from langchain_core.runnables import Runnable
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore

# common tools imports
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.llm_helper import Llm
from common_tools.models.llm_info import LlmInfo
from common_tools.helpers.file_helper import file
from common_tools.helpers.env_helper import EnvHelper
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.models.embedding_model import EmbeddingModel
from common_tools.models.embedding_model_factory import EmbeddingModelFactory
from common_tools.models.vector_db_type import VectorDbType

class RagService:
    def __init__(self, llms_or_info: Optional[Union[LlmInfo, Runnable, list]], embedding_model:EmbeddingModel= None, vector_db_base_path:str = None, vector_db_type:VectorDbType = VectorDbType('chroma'), vector_db_name:str = 'main', documents_json_filename:str = None):
        # Init default parameters values if not setted
        if not vector_db_base_path: vector_db_base_path = './storage'
        if not documents_json_filename: documents_json_filename = 'bm25_documents.json'
        self.llms_infos: list[LlmInfo] = None
        self.llm_1=None
        self.llm_2=None
        self.llm_3=None
        self.instanciate_embedding(embedding_model)
        self.instanciate_llms(llms_or_info, test_llms_inference=False)
        self.vector_db_name:str = vector_db_name
        self.vector_db_type:VectorDbType = vector_db_type
        self.vector_db_base_path:str = vector_db_base_path
        self.vector_db_path:str = os.path.join(os.path.join(os.path.abspath(vector_db_base_path), self.embedding_model_name), vector_db_type.value)
        self.all_documents_json_file_path = os.path.abspath(os.path.join(vector_db_base_path, documents_json_filename))

        self.langchain_documents:list[Document] = self.load_raw_langchain_documents(self.all_documents_json_file_path)
        self.vectorstore:VectorStore = self.load_vectorstore(self.vector_db_path, self.embedding, self.vector_db_type, self.vector_db_name)

    def instanciate_embedding(self, embedding_model:EmbeddingModel):
        self.embedding = EmbeddingModelFactory.create_instance(embedding_model)
        self.embedding_model_name = embedding_model.model_name
        
    def instanciate_llms(self, llm_or_infos: Optional[Union[LlmInfo, Runnable, list]], test_llms_inference:bool = False):        
        if isinstance(llm_or_infos, list):
            if any(llm_or_infos) and isinstance(llm_or_infos[0], LlmInfo):
                self.llms_infos = llm_or_infos
            index = 1
            for llm_or_info in llm_or_infos:
                if index == 1:
                    self.llm_1 = self.init_llm(llm_or_info, test_llms_inference)
                elif index == 2:
                    self.llm_2 = self.init_llm(llm_or_info, test_llms_inference)
                elif index == 3:
                    self.llm_3 = self.init_llm(llm_or_info, test_llms_inference)
                else:
                    raise ValueError("Only 4 llms are supported")
                index += 1
        else:
            self.llm_1 = self.init_llm(llm_or_infos)
        
        #set default llms if undefined
        if not self.llm_2: self.llm_2 = self.llm_1
        if not self.llm_3: self.llm_3 = self.llm_2
    
    def init_llm(self, llm_or_info: Optional[Union[LlmInfo, Runnable]], test_inference:bool = False) -> Runnable:
        if isinstance(llm_or_info, LlmInfo) or (isinstance(llm_or_info, list) and any(llm_or_info) and isinstance(llm_or_info[0], LlmInfo)):            
            llm = LangChainFactory.create_llms_from_infos(llm_or_info)[0]
            if test_inference:
                if not Llm.test_llm_inference(llm):                    
                    model_name = llm.model_name if hasattr(llm, 'model_name') else llm.model if hasattr(llm, 'model') else llm.__class__.__name__
                    raise ValueError(f"Inference test failed for model: '{model_name}'.")
            return llm
        elif isinstance(llm_or_info, Runnable):
            return llm_or_info
        else:
            raise ValueError("Invalid llm_or_infos parameter")
  
    def load_raw_langchain_documents(self, filepath:str = None) -> List[Document]:
        if not file.exists(filepath):
            txt.print(">>> No file found for loading langchain documents. Please generate them first or provide a valid file path.")
            return None
                        
        json_as_str = file.read_file(filepath)
        json_data = json.loads(json_as_str)
        docs = [
            Document(page_content=doc["page_content"], metadata=doc["metadata"]) 
            for doc in json_data 
        ]
        return docs
    
    def load_vectorstore(self, vector_db_path:str = None, embedding: Embeddings = None, vectorstore_type: VectorDbType = VectorDbType('chroma'), vectorstore_name:str = 'main') -> VectorStore:
        try:
            is_cloud_hosted_db = vectorstore_type == VectorDbType.Pinecone # TODO: to generalize
            vectorstore:VectorStore = None

            if not is_cloud_hosted_db:
                vector_db_path = os.path.join(vector_db_path, vectorstore_name)
                if not file.exists(vector_db_path): 
                    txt.print(f'>> Vectorstore not loaded, as path: "... {vector_db_path[-110:]}" is not found')
            
            if vectorstore_type == VectorDbType.ChromaDB:
                from langchain_chroma import Chroma
                #
                vectorstore = Chroma(persist_directory= vector_db_path, embedding_function= embedding)
            
            elif vectorstore_type == VectorDbType.Qdrant:
                from qdrant_client import QdrantClient
                from langchain_qdrant import QdrantVectorStore
                #
                qdrant_client = QdrantClient(path=vector_db_path)
                vectorstore = QdrantVectorStore(client=qdrant_client, collection_name=vectorstore_name, embedding=embedding)
            
            elif vectorstore_type == VectorDbType.Pinecone:
                import pinecone
                from pinecone import ServerlessSpec
                from langchain_pinecone import PineconeVectorStore
                #
                pinecone_instance = pinecone.Pinecone(api_key= EnvHelper.get_pinecone_api_key()) #, environment= EnvHelper.get_pinecone_environment()                
                is_native_hybrid_search = EnvHelper.get_is_common_db_for_sparse_and_dense_vectors()
                if is_native_hybrid_search:
                    vectorstore_name += '-hybrid' # make the index name specific in case of native hybrid search (both sparse & dense vectors in the same record)
                
                # Create the DB (Pinecone's index) if it doesn't exist yet
                if vectorstore_name not in pinecone_instance.list_indexes().names():
                    embedding_vector_size = len(self.embedding.embed_query("test"))                    
                    pinecone_instance.create_index(
                                        name= vectorstore_name, 
                                        dimension=embedding_vector_size,
                                        metric= "dotproduct" if is_native_hybrid_search else "cosine",
                                        #pod_type="s1",
                                        spec=ServerlessSpec(
                                                cloud='aws',
                                                region='us-east-1'
                                        )
                    )
                    
                    while not pinecone_instance.describe_index(vectorstore_name).status['ready']:
                        time.sleep(1)
                    
                pinecone_index = pinecone_instance.Index(name=vectorstore_name)
                print(f"Loaded Pinecone vectorstore: '{vectorstore_name}' index, containing " + str(pinecone_index.describe_index_stats()['total_vector_count']) + " vectors total.")
                vectorstore = PineconeVectorStore(index=pinecone_index, embedding=self.embedding)
            return vectorstore
        
        except Exception as e:
            txt.print(f"/!\\ Loading vectorstore fails /!\\: {e}")
            return None