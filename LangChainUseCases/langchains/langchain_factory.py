from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatOllama, ChatAnthropic
from langchain_groq import ChatGroq
#import google.generative
#from langchain_google_genai import GoogleGenerativeAI
from langchain_core.language_models import BaseChatModel
from helpers.txt_helper import txt
from langchains.langchain_adapter_type import LangChainAdapterType
import uuid

from models.llm_info import LlmInfo

class LangChainFactory():
    @staticmethod
    def create_llms_from_infos(llms_infos: list[LlmInfo]) -> list[BaseChatModel]:
        txt.print_with_spinner(f"Loading LLM model ...")
        if isinstance(llms_infos, LlmInfo):
            llms_infos = [llms_infos]
        if len(llms_infos) == 0:
            raise ValueError("No LLM info provided.")

        llms: list[BaseChatModel] = []
        for llm_info in llms_infos:
            llm = LangChainFactory.create_llm(
                adapter_type= llm_info.type,
                llm_model_name= llm_info.model,
                timeout_seconds= llm_info.timeout,
                temperature= llm_info.temperature,
                api_key= llm_info.api_key)
            llms.append(llm)
        txt.stop_spinner_replace_text("LLM model loaded successfully.")
        return llms
    
    @staticmethod
    def create_llm(adapter_type: LangChainAdapterType, llm_model_name: str, timeout_seconds: int = 50, temperature: float = 0.1, api_key: str = None) -> BaseChatModel:
        llm: BaseChatModel = None
        if adapter_type == LangChainAdapterType.OpenAI:
            llm = LangChainFactory.create_llm_openai(llm_model_name, api_key, timeout_seconds, temperature)
        elif adapter_type == LangChainAdapterType.Ollama:
            llm = LangChainFactory.create_llm_ollama(llm_model_name, timeout_seconds, temperature)
        elif adapter_type == LangChainAdapterType.Groq:
            llm = LangChainFactory.create_llm_groq(llm_model_name, api_key, timeout_seconds, temperature)
        elif adapter_type == LangChainAdapterType.Google:
            llm = LangChainFactory.create_llm_google(llm_model_name, api_key, timeout_seconds, temperature)
        elif adapter_type == LangChainAdapterType.Anthropic:
            llm = LangChainFactory.create_llm_anthropic(llm_model_name, api_key, timeout_seconds, temperature)
        else:
            raise ValueError(f"Unknown adapter type: {adapter_type}")
        return llm
 
 
    @staticmethod
    def create_llm_openai(llm_model_name: str, api_key: str, timeout_seconds: int = 50, temperature:float = 0.1) -> ChatOpenAI:
        return ChatOpenAI(    
            name= f"chat_openai_{str(uuid.uuid4())}",
            model_name= llm_model_name,
            request_timeout= timeout_seconds,
            temperature= temperature,
            openai_api_key= api_key,
        )
    
    @staticmethod
    def create_llm_ollama(llm_model_name: str, timeout_seconds: int = 50, temperature:float = 0.1) -> ChatOllama:
        return ChatOllama(    
            name= f"ollama_{str(uuid.uuid4())}",
            model= llm_model_name,
            timeout= timeout_seconds,
            temperature= temperature
        )
        
    @staticmethod
    def create_llm_anthropic(llm_model_name: str, api_key: str, timeout_seconds: int = 50, temperature:float = 0.1) -> ChatAnthropic:
        return ChatAnthropic(    
            name= f"anthropic_{str(uuid.uuid4())}",
            model= llm_model_name,
            default_request_timeout= timeout_seconds,
            temperature= temperature,
            anthropic_api_key= api_key,
        )
        
    @staticmethod     
    def create_llm_groq(llm_model_name: str, api_key: str, timeout_seconds: int = 50, temperature:float = 0.1) -> ChatGroq:
        return ChatGroq(    
            name= f"chat_groq_{str(uuid.uuid4())}",
            model_name= llm_model_name,
            request_timeout= timeout_seconds,
            temperature= temperature,
            groq_api_key= api_key,
        )
        
    @staticmethod     
    def create_llm_google(llm_model_name: str, api_key: str, timeout_seconds: int = 50, temperature:float = 0.1):# -> GoogleGenerativeAI:
        pass
        # return GoogleGenerativeAI(    
        #     name= f"chat_google_{str(uuid.uuid4())}",
        #     model= llm_model_name,
        #     timeout= timeout_seconds,
        #     temperature= temperature,
        #     google_api_key= api_key,
        # )