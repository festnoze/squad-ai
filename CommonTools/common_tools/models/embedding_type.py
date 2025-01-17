from enum import Enum

class EmbeddingType(Enum):
    OpenAI = "OpenAI"
    Ollama = "Ollama"
    SentenceTransformer = "SentenceTransformer"