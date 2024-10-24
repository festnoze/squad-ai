# common tools import
from common_tools.helpers.file_helper import file
from common_tools.langchains.langsmith_client import Langsmith
from common_tools.helpers.llm_helper import Llm
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.groq_helper import GroqHelper
from common_tools.models.langchain_adapter_type import LangChainAdapterType
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.models.llm_info import LlmInfo
# internal import
from services.summary_generation_service import SummaryGenerationService

# external imports
import openai
import os
from dotenv import find_dotenv, load_dotenv

class Startup:
    is_initialized = False
    llms_infos: list[LlmInfo] = []

    def __init__(self):
        pass

    @staticmethod
    def initialize():
        if Startup.is_initialized:
            return Startup.llms_infos
        Startup.is_initialized = True

        load_dotenv(find_dotenv())

        openai_api_key = os.getenv("OPEN_API_KEY")
        groq_api_key = os.getenv("GROQ_API_KEY")
        google_api_key = os.getenv("GOOGLE_API_KEY")
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        #openai.api_key = openai_api_key

        # Select the LLMs to be used for first and fallbacks uses
        #Startup.llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "phi3", timeout= 80, temperature = 0.5))
        #Startup.llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "llama2",  timeout= 200, temperature = 0.5))
        #Startup.llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "llama3", timeout= 200, temperature = 0.5))
        #Startup.llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "mistral",  timeout= 200, temperature = 0.5))
        #Startup.llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "mixtral",  timeout= 500, temperature = 0.5))
        #Startup.llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "dolphin-mixtral",  timeout= 400, temperature = 0.5))
        #Startup.llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "nous-hermes2", timeout= 200, temperature = 0.5))
        #Startup.llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "openhermes", timeout= 200, temperature = 0.5))

        #Startup.llms_infos.append(LlmInfo(type= LangChainAdapterType.Groq, model= "mixtral-8x7b-32768",  timeout= 20, temperature = 0.5))
        #Startup.llms_infos.append(LlmInfo(type= LangChainAdapterType.Groq, model= "llama3-8b-8192",  timeout= 10, temperature = 0.5))
        #Startup.llms_infos.append(LlmInfo(type= LangChainAdapterType.Groq, model= "llama3-70b-8192",  timeout= 20, temperature = 0.5))

        #Startup.llms_infos.append(LlmInfo(type= LangChainAdapterType.Google, model= "gemini-pro",  timeout= 60, temperature = 0.5))

        #Startup.llms_infos.append(LlmInfo(type= LangChainAdapterType.Anthropic, model= "claude-2",  timeout= 60, temperature = 0.5))
        #Startup.llms_infos.append(LlmInfo(type= LangChainAdapterType.Anthropic, model= "claude-3-opus-20240229",  timeout= 60, temperature = 0.5))

        #Startup.llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo-0125",  timeout= 60, temperature = 0.5))
        #Startup.llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo",  timeout= 60, temperature = 0.5))
        #Startup.llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4-turbo",  timeout= 120, temperature = 0.5))
        Startup.llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4o",  timeout= 80, temperature = 1))
        Startup.llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4o",  timeout= 80, temperature = 0.1))

        print("Starting...")

        # langsmith = Langsmith()
        # langsmith.delete_all_project_sessions()
        ##langsmith.create_project()

        #AvailableActions.display_menu_and_actions(Startup.llms_infos, 4)

        return Startup.llms_infos