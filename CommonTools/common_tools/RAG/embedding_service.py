import os
from typing import Any
from langchain.embeddings import OpenAIEmbeddings, OllamaEmbeddings
from langchain_community.embeddings.sentence_transformer import SentenceTransformerEmbeddings
from common_tools.models.embedding_type import EmbeddingModel, EmbeddingType

class EmbeddingService:
    @staticmethod
    def get_embedding(embedding_model: EmbeddingModel, api_key:str = None) -> Any:
        if not embedding_model:
            embedding_model = EmbeddingModel.Ollama_AllMiniLM
        
        if embedding_model.is_openai:
            if not api_key:
                api_key= os.getenv("OPEN_API_KEY") 
                if not api_key:
                    raise ValueError("Required OpenAI API key isn't provided, nor being found in the env.")
            return OpenAIEmbeddings(model=embedding_model.model_name, api_key=api_key)

        if embedding_model.is_ollama:
            return OllamaEmbeddings(model=embedding_model.model_name)
        
        if embedding_model.is_sentence_transformer:
            return SentenceTransformerEmbeddings(model_name=f"sentence-transformers/{embedding_model.model_name}")

        raise ValueError(f"Unhandled embedding type: '{embedding_model.embedding_type}'")
