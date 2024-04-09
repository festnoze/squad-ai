from langchain_openai import ChatOpenAI
import uuid
# internal imports
from langchains.langchain_adapter_type import LangChainAdapterType
from langchains.langchain_adapter_base import LangChainAdapter

class LangChainAdapterForOpenAI(LangChainAdapter):
    def __init__(self, llm_model_name: str, api_key: str):
        self.adapter_type = LangChainAdapterType.OpenAI
        self.llm_model_name = llm_model_name
        self.api_key = api_key
        self.llm: ChatOpenAI = self.create_langchain_llm(llm_model_name)

    def create_langchain_llm(self, llm_model_name: str, timeout_seconds: int = 50, temperature:float = 0.1) -> ChatOpenAI:
        return ChatOpenAI(    
            name= f"chat_openai_{str(uuid.uuid4())}",
            model= llm_model_name,
            timeout= timeout_seconds,
            temperature= temperature,
            api_key= self.api_key,
        )