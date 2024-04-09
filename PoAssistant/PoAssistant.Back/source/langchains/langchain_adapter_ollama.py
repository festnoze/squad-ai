from langchain.llms.ollama  import Ollama
import uuid
# internal imports
from langchains.langchain_adapter_base import LangChainAdapter
from langchains.langchain_adapter_type import LangChainAdapterType

class LangChainAdapterForOllama(LangChainAdapter):
    def __init__(self, llm_model_name: str):
        self.adapter_type = LangChainAdapterType.Ollama
        self.llm_model_name = llm_model_name
        self.llm: Ollama = self.create_langchain_llm(llm_model_name)

    def create_langchain_llm(self, llm_model_name: str, timeout_seconds: int = 50, temperature:float = 0.1) -> Ollama:
        return Ollama(    
            name= f"ollama_{str(uuid.uuid4())}",
            model= llm_model_name,
            timeout= timeout_seconds,
            temperature= temperature,
            #callback_manager= CallbackManager([StreamingStdOutCallbackHandler()]) # display answer's steam to the console
        )