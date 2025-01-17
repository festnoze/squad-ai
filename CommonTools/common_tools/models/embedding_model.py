from enum import Enum
from common_tools.models.embedding_type import EmbeddingType

class EmbeddingModel(Enum):
    # OpenAI models
    OpenAI_Ada = ("text-embedding-ada-002", EmbeddingType.OpenAI)
    OpenAI_Babbage = ("text-embedding-babbage-001", EmbeddingType.OpenAI)
    OpenAI_Curie = ("text-embedding-curie-001", EmbeddingType.OpenAI)
    OpenAI_Davinci = ("text-embedding-davinci-001", EmbeddingType.OpenAI)
    OpenAI_TextEmbedding3Small = ("text-embedding-3-small", EmbeddingType.OpenAI)   # New model added
    OpenAI_TextEmbedding3Large = ("text-embedding-3-large", EmbeddingType.OpenAI)   # New model added

    # Ollama models
    Ollama_AllMiniLM = ("all-minilm", EmbeddingType.Ollama)
    Ollama_Llama3 = ("llama3", EmbeddingType.Ollama)
    Ollama_GPTJ = ("gpt-j-6b", EmbeddingType.Ollama)   
    Ollama_Mistral = ("mistral", EmbeddingType.Ollama)   
    Ollama_E5_Small = ("e5-small", EmbeddingType.Ollama) 
    Ollama_E5_Large_Multilingual_F16 = ("jeffh/intfloat-multilingual-e5-large:f16", EmbeddingType.Ollama)

    # SentenceTransformer models
    SentenceTransformer_AllMiniML_L6 = ("all-MiniLM-L6-v2", EmbeddingType.SentenceTransformer)
    SentenceTransformer_MpNetBase = ("all-mpnet-base-v2", EmbeddingType.SentenceTransformer)
    SentenceTransformer_AllMiniML_L12 = ("all-MiniLM-L12-v2", EmbeddingType.SentenceTransformer)
    SentenceTransformer_MiniML_Paraphrase_Multilingual_L12 = ("paraphrase-multilingual-MiniLM-L12-v2", EmbeddingType.SentenceTransformer)

    @property
    def model_name(self):
        return self.value[0]

    @property
    def embedding_type(self):
        return self.value[1]
    
    def __str__(self):
        return f"{self.model_name} ({self.embedding_type.value})"
    
    @property
    def is_openai(self) -> bool:
        return self.embedding_type == EmbeddingType.OpenAI

    @property
    def is_ollama(self) -> bool:
        return self.embedding_type == EmbeddingType.Ollama
    
    @property
    def is_sentence_transformer(self) -> bool:
        return self.embedding_type == EmbeddingType.SentenceTransformer