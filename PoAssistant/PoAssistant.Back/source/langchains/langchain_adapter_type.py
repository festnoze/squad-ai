from enum import Enum

class LangChainAdapterType(Enum):
    OpenAI = "OpenAI"
    Ollama = "Ollama"
    Groq = "Groq"