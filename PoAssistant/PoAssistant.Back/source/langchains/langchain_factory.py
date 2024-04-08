from langchains.langchain_adapter_interface import LangChainAdapter
from langchains.langchain_adapter_ollama import LangChainAdapterForOllama
from langchains.langchain_adapter_openai import LangChainAdapterForOpenAI
from langchains.langchain_adapter_type import LangChainAdapterType

class LangChainFactory:
    def get_langchain_adapter(adapter_type: LangChainAdapterType, llm_model_name: str, api_key: str) -> LangChainAdapter:
        if adapter_type == LangChainAdapterType.OpenAI:
            return LangChainAdapterForOpenAI(llm_model_name, api_key)
        elif adapter_type == LangChainAdapterType.Ollama:
            return LangChainAdapterForOllama(llm_model_name)