from enum import Enum

class LangChainAdapterType(Enum):
    OpenAI = "OpenAI"
    Ollama = "Ollama"
    Google = "Google"
    Anthropic = "Anthropic"
    Groq = "Groq"