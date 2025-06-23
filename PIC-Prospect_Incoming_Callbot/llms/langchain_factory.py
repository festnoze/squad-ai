#### DUPLICATE FROM COMMON TOOLS ####

import uuid
import logging
#
from langchain_core.runnables import Runnable
from langchain_core.language_models.chat_models import BaseChatModel
#
from llms.llm_info import LlmInfo
from llms.langchain_adapter_type import LangChainAdapterType

class LangChainFactory():
    logger = logging.getLogger(__name__)
    @staticmethod
    def create_llms_from_infos(llms_infos: list[LlmInfo]) -> list[Runnable]:
        LangChainFactory.logger.info(f'Loading LLM models ...')
        if isinstance(llms_infos, LlmInfo):
            llms_infos = [llms_infos]
        if len(llms_infos) == 0:
            raise ValueError('No LLMs infos provided.')

        llms: list[Runnable] = []
        for llm_info in llms_infos:
            llm = LangChainFactory.create_llm_from_info(llm_info)
            llms.append(llm)
            
        LangChainFactory.logger.info('Loaded LLM model(s): ' + ', '.join([llm_info.model for llm_info in llms_infos]))
        return llms
    
    @staticmethod
    def create_llm_from_info(llm_info: LlmInfo) -> Runnable:
        LangChainFactory.logger.info(f'Loading LLM model ...')
        llm = LangChainFactory.create_llm(
            adapter_type= llm_info.type,
            llm_model_name= llm_info.model,
            timeout_seconds= llm_info.timeout,
            temperature= llm_info.temperature,
            inference_provider_api_key= llm_info.api_key,
            extra_body_dict= llm_info.extra_params,
        )
        LangChainFactory.logger.info('LLM model loaded successfully.')
        return llm
    
    @staticmethod
    def create_llm(adapter_type: LangChainAdapterType, llm_model_name: str, timeout_seconds: int = 50, temperature: float = 0.1, inference_provider_api_key: str = None, extra_body_dict: dict[str, any] = {}) -> Runnable:
        llm: Runnable = None
        if adapter_type == LangChainAdapterType.OpenAI:
            if not inference_provider_api_key: 
                raise ValueError(f'"{LangChainFactory.__name__}" requires that "type" of {LlmInfo.__name__} (of type: "{LangChainAdapterType.__name__}") to have its "api_key" property specified for adapter: {LangChainAdapterType.OpenAI}')
            llm = LangChainFactory.create_openai_llm(llm_model_name, inference_provider_api_key, timeout_seconds, temperature)

        elif adapter_type == LangChainAdapterType.InferenceProvider:
            if not adapter_type.default_inference_provider_name:
                raise ValueError(f'"{LangChainFactory.__name__}" requires that "type" of {LlmInfo.__name__} (of type: "{LangChainAdapterType.__name__}") to have its "default_inference_provider_name" property specified for adapter: {LangChainAdapterType.InferenceProvider}')
            
            if adapter_type.default_inference_provider_name == 'OpenRouter':
                inference_provider_api_key = EnvHelper.get_openrouter_api_key()
                inference_provider_base_url = EnvHelper.get_openrouter_base_url()
            else:
                raise ValueError(f'"{LangChainFactory.__name__}" cannot handle inference provider: {adapter_type.default_inference_provider_name}')
            
            llm = LangChainFactory.create_inference_provider_generic_openai_llm(llm_model_name, inference_provider_base_url, inference_provider_api_key, timeout_seconds, temperature, extra_body_dict)

        elif adapter_type == LangChainAdapterType.Ollama:
            llm = LangChainFactory.create_ollama_llm(llm_model_name, timeout_seconds, temperature)

        elif adapter_type == LangChainAdapterType.Groq:            
            if not inference_provider_api_key: inference_provider_api_key = EnvHelper.get_groq_api_key()
            llm = LangChainFactory.create_groq_llm(llm_model_name, inference_provider_api_key, timeout_seconds, temperature)

        elif adapter_type == LangChainAdapterType.Google:
            raise ValueError('Google adapter is not implemented yet.')
            llm = LangChainFactory.create_google_llm(llm_model_name, inference_provider_api_key, timeout_seconds, temperature)

        elif adapter_type == LangChainAdapterType.Anthropic:            
            if not inference_provider_api_key: inference_provider_api_key = EnvHelper.get_anthropic_api_key()
            llm = LangChainFactory.create_anthropic_llm(llm_model_name, inference_provider_api_key, timeout_seconds, temperature)

        else:
            raise ValueError(f'Unknown adapter type: {adapter_type}')
        return llm
 
    @staticmethod
    def create_openai_llm(llm_model_name: str, api_key: str, timeout_seconds: int = 50, temperature:float = 0.1) -> BaseChatModel:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(    
            name= f'openai_chat_{str(uuid.uuid4())}',
            model_name= llm_model_name,
            request_timeout= timeout_seconds,
            temperature= temperature,
            openai_api_key= api_key,
        )
    
    @staticmethod
    def create_inference_provider_generic_openai_llm(llm_model_name: str, inference_provider_base_url:str, inference_provider_api_key: str, timeout_seconds: int = 50, temperature:float = 0.1, extra_body_dict: dict[str, any] = {}) -> BaseChatModel:
        from langchain_openai import ChatOpenAI
        # base_model_kwargs: dict[str, any] = {
        #     "headers": {
        #         "HTTP-Referer": "OUR_SITE_URL",
        #         "X-Title": "OUR_SITE_NAME"
        #     }
        # }
        return ChatOpenAI(
            name=f"generic_openai_chat_{str(uuid.uuid4())}",
            openai_api_key=inference_provider_api_key,
            openai_api_base=inference_provider_base_url,
            model_name=llm_model_name,
            request_timeout=timeout_seconds,
            temperature=temperature,
            extra_body= extra_body_dict,
            #model_kwargs=base_model_kwargs,
        )    
    
    @staticmethod
    def create_ollama_llm(llm_model_name: str, timeout_seconds: int = 50, temperature:float = 0.1) -> BaseChatModel:
        from langchain_ollama import ChatOllama
        return ChatOllama(    
            name= f'ollama_chat_{str(uuid.uuid4())}',
            model= llm_model_name,
            timeout= timeout_seconds,
            temperature= temperature
        )
          
    @staticmethod
    def create_anthropic_llm(llm_model_name: str, api_key: str, timeout_seconds: int = 50, temperature:float = 0.1) -> BaseChatModel:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(    
            name= f'anthropic_chat_{str(uuid.uuid4())}',
            model= llm_model_name,
            default_request_timeout= timeout_seconds,
            temperature= temperature,
            anthropic_api_key= api_key,
        )
    
    @staticmethod     
    def create_groq_llm(llm_model_name: str, api_key: str, timeout_seconds: int = 50, temperature:float = 0.1) -> BaseChatModel:
        from langchain_groq import ChatGroq
        return ChatGroq(    
            name= f'groq_chat_{str(uuid.uuid4())}',
            model_name= llm_model_name,
            request_timeout= timeout_seconds,
            temperature= temperature,
            groq_api_key= api_key,
        )
        
    @staticmethod     
    def create_llm_google(llm_model_name: str, api_key: str, timeout_seconds: int = 50, temperature:float = 0.1):# -> BaseChatModel:
        pass
        # return GoogleGenerativeAI(    
        #     name= f'chat_google_{str(uuid.uuid4())}',
        #     model= llm_model_name,
        #     timeout= timeout_seconds,
        #     temperature= temperature,
        #     google_api_key= api_key,
        # )