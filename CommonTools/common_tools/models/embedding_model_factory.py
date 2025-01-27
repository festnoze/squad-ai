from langchain_community.embeddings import OllamaEmbeddings
from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings.sentence_transformer import SentenceTransformerEmbeddings
from langchain_core.embeddings import Embeddings
from common_tools.helpers.env_helper import EnvHelper
from common_tools.models.embedding_model import EmbeddingModel
    
class EmbeddingModelFactory:
    @staticmethod
    def create_instance(embedding_model:EmbeddingModel, api_key:str = None) -> Embeddings:
        if embedding_model.is_openai:
            if not api_key:
                api_key= EnvHelper.get_openai_api_key() 
            return OpenAIEmbeddings(model=embedding_model.model_name, api_key=api_key)

        if embedding_model.is_ollama:
            return OllamaEmbeddings(model=embedding_model.model_name)
        
        if embedding_model.is_sentence_transformer:
            return SentenceTransformerEmbeddings(model_name=f"sentence-transformers/{embedding_model.model_name}")

        raise ValueError(f"Unhandled embedding type: '{embedding_model.embedding_type}'")

