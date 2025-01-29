from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from langchain_anthropic import ChatAnthropic
from langchain_groq import ChatGroq
from langchain_core.runnables import Runnable
import uuid
#import google.generative
#from langchain_google_genai import GoogleGenerativeAI
#
from common_tools.models.llm_info import LlmInfo
from common_tools.models.langchain_adapter_type import LangChainAdapterType
from common_tools.helpers.env_helper import EnvHelper
from common_tools.helpers.txt_helper import txt

import os
from dotenv import load_dotenv
import openai

class LangChainFactory():
    @staticmethod
    def set_openai_apikey():
        if not 'OPENAI_API_KEY' in os.environ:
            openai_api_key = EnvHelper.get_openai_api_key()     
            openai.api_key = openai_api_key

    @staticmethod
    def create_llms_from_infos(llms_infos: list[LlmInfo]) -> list[Runnable]:
        txt.print_with_spinner(f'Loading LLM models ...')
        if isinstance(llms_infos, LlmInfo):
            llms_infos = [llms_infos]
        if len(llms_infos) == 0:
            raise ValueError('No LLMs infos provided.')

        llms: list[Runnable] = []
        activate_print_status = txt.activate_print
        txt.activate_print = False

        for llm_info in llms_infos:
            llm = LangChainFactory.create_llm_from_info(llm_info)
            llms.append(llm)
            
        txt.activate_print = activate_print_status
        txt.stop_spinner_replace_text('Loaded LLM model(s): ' + ', '.join([llm_info.model for llm_info in llms_infos]))
        return llms
    
    @staticmethod
    def create_llm_from_info(llm_info: LlmInfo) -> Runnable:
        txt.print_with_spinner(f'Loading LLM model ...')
        llm = LangChainFactory.create_llm(
            adapter_type= llm_info.type,
            llm_model_name= llm_info.model,
            timeout_seconds= llm_info.timeout,
            temperature= llm_info.temperature,
            inference_provider_api_key= llm_info.api_key)
        txt.stop_spinner_replace_text('LLM model loaded successfully.')
        return llm
    
    @staticmethod
    def create_llm(adapter_type: LangChainAdapterType, llm_model_name: str, timeout_seconds: int = 50, temperature: float = 0.1, inference_provider_api_key: str = None) -> Runnable:
        llm: Runnable = None
        if adapter_type == LangChainAdapterType.OpenAI:
            if not inference_provider_api_key: inference_provider_api_key = EnvHelper.get_openai_api_key()
            llm = LangChainFactory.create_openai_llm(llm_model_name, inference_provider_api_key, timeout_seconds, temperature)

        elif adapter_type == LangChainAdapterType.InferenceProvider:
            if not adapter_type.default_inference_provider_name:
                raise ValueError(f'"{LangChainFactory.__name__}" requires that "type" of {LlmInfo.__name__} (of type: "{LangChainAdapterType.__name__}") to have its "default_inference_provider_name" property specified for adapter: {LangChainAdapterType.InferenceProvider}')
            
            if adapter_type.default_inference_provider_name == 'OpenRouter':
                inference_provider_api_key = EnvHelper.get_openrouter_api_key()
                inference_provider_base_url = EnvHelper.get_openrouter_base_url()
            else:
                raise ValueError(f'"{LangChainFactory.__name__}" cannot handle inference provider: {adapter_type.default_inference_provider_name}')
            
            llm = LangChainFactory.create_inference_provider_generic_openai_llm(llm_model_name, inference_provider_base_url, inference_provider_api_key, timeout_seconds, temperature)

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
    def create_openai_llm(llm_model_name: str, api_key: str, timeout_seconds: int = 50, temperature:float = 0.1) -> ChatOpenAI:
        return ChatOpenAI(    
            name= f'chat_openai_{str(uuid.uuid4())}',
            model_name= llm_model_name,
            request_timeout= timeout_seconds,
            temperature= temperature,
            openai_api_key= api_key,
        )
    
    @staticmethod
    def create_inference_provider_generic_openai_llm(llm_model_name: str, inference_provider_base_url:str, inference_provider_api_key: str, timeout_seconds: int = 50, temperature:float = 0.1) -> ChatOpenAI:
        return ChatOpenAI(
            name= f'chat_generic_openai_{str(uuid.uuid4())}',
            openai_api_key=inference_provider_api_key,
            openai_api_base=inference_provider_base_url,
            model_name=llm_model_name,
            request_timeout= timeout_seconds,
            temperature= temperature,
            # model_kwargs={
            #     "headers": {
            #     "HTTP-Referer": "OUR_SITE_URL",
            #     "X-Title": "OUR_SITE_NAME",
            #     }
            # },
        )
    
    @staticmethod
    def create_ollama_llm(llm_model_name: str, timeout_seconds: int = 50, temperature:float = 0.1) -> ChatOllama:
        return ChatOllama(    
            name= f'ollama_{str(uuid.uuid4())}',
            model= llm_model_name,
            timeout= timeout_seconds,
            temperature= temperature
        )
          
    @staticmethod
    def create_anthropic_llm(llm_model_name: str, api_key: str, timeout_seconds: int = 50, temperature:float = 0.1) -> ChatOllama:
        return ChatAnthropic(    
            name= f'anthropic_{str(uuid.uuid4())}',
            model= llm_model_name,
            default_request_timeout= timeout_seconds,
            temperature= temperature,
            anthropic_api_key= api_key,
        )
    
    @staticmethod     
    def create_groq_llm(llm_model_name: str, api_key: str, timeout_seconds: int = 50, temperature:float = 0.1) -> ChatGroq:
        return ChatGroq(    
            name= f'chat_groq_{str(uuid.uuid4())}',
            model_name= llm_model_name,
            request_timeout= timeout_seconds,
            temperature= temperature,
            groq_api_key= api_key,
        )
        
    @staticmethod     
    def create_llm_google(llm_model_name: str, api_key: str, timeout_seconds: int = 50, temperature:float = 0.1):# -> GoogleGenerativeAI:
        pass
        # return GoogleGenerativeAI(    
        #     name= f'chat_google_{str(uuid.uuid4())}',
        #     model= llm_model_name,
        #     timeout= timeout_seconds,
        #     temperature= temperature,
        #     google_api_key= api_key,
        # )