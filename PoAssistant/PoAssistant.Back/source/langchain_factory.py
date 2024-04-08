from langchain_adapter_interface import LangChainAdapter
from langchain_ollama_adapter import LangChainOllamaAdapter
from langchain_openai_adapter import LangChainOpenAIAdapter

class LangChainFactory:
    def get_langchain_adapter(llm_type: str) -> LangChainAdapter:
        if llm_type.lower() == "openai":
            return LangChainOpenAIAdapter()
        elif llm_type.lower() == "ollama":
            return LangChainOllamaAdapter()
        else:
            raise ValueError("Invalid adapter type")