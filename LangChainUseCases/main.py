# internal import
import time
from csharp_code_splitter import CSharpCodeSplit
from helpers.file_helper import file
from helpers.groq_helper import GroqHelper
from helpers.tools_helpers import ToolsContainer, ToolsHelper
from helpers.txt_helper import txt
from helpers.c_sharp_helpers import CSharpXMLDocumentation, CSharpXMLDocumentationFactory
from langchains.langchain_factory import LangChainFactory
from langchains.langchain_adapter_type import LangChainAdapterType
from models.class_desc import ClassDesc
from models.llm_info import LlmInfo
from models.param_doc import ParameterDocumentation, ParameterDocumentationPydantic
from models.params_doc import MethodParametersDocumentation, MethodParametersDocumentationPydantic
from summarize import Summarize

# external imports
import openai
import os
from dotenv import find_dotenv, load_dotenv
from langchain_community.callbacks import get_openai_callback, OpenAICallbackHandler

# Text splitters
from langchain.text_splitter import CharacterTextSplitter
from langchain_community.document_loaders import TextLoader
import yfinance as yf

# Load environment variables from .env file
print("Started")

load_dotenv(find_dotenv())

# Set api keys
groq_api_key = os.getenv("GROQ_API_KEY")
openai_api_key = os.getenv("OPEN_API_KEY")
openai.api_key = openai_api_key

# Select the LLM to be used
llm_infos = LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo-0613",  timeout= 60, api_key= openai_api_key)
#llm_infos = LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4-turbo-2024-04-09",  timeout= 120, api_key= openai_api_key)

#llm_infos = LlmInfo(type= LangChainAdapterType.Groq, model= "mixtral-8x7b-32768",  timeout= 20, api_key= groq_api_key)
#llm_infos = LlmInfo(type= LangChainAdapterType.Groq, model= "llama3-8b-8192",  timeout= 10, api_key= groq_api_key)
#llm_infos = LlmInfo(type= LangChainAdapterType.Groq, model= "llama3-70b-8192",  timeout= 20, api_key= groq_api_key)

#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "phi3", timeout= 20, api_key= None)
#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "llama3", timeout= 200, api_key= None)
#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "llama2",  timeout= 200, api_key= None)
#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "mistral",  timeout= 200, api_key= None)
#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "mixtral",  timeout= 500, api_key= None)
#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "dolphin-mixtral",  timeout= 400, api_key= None)
#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "nous-hermes2", timeout= 200, api_key= None)
#llm_infos = LlmInfo(type= LangChainAdapterType.Ollama, model= "openhermes", timeout= 200, api_key= None)

def run_main():
    # Instanciate the LLM
    llm = LangChainFactory.create_llm(
        adapter_type= llm_infos.type,
        llm_model_name= llm_infos.model,
        timeout_seconds= llm_infos.timeout,
        temperature= 0.0,
        api_key= llm_infos.api_key)

    # Test Groq through its own client (no langchain)
    #GroqHelper.test_query(llm_infos)

    ## Use web search tool
    # from langchain_community.utilities import GoogleSerperAPIWrapper
    # web_search = GoogleSerperAPIWrapper()
    # res = web_search.run("what's Obama's first name?")
    # print(res)

    ## Use tools through agent executor
    #ToolsHelper.test_agent_executor_with_tools(llm)

    # Summarize short text
    # text = file.get_as_str("short-text.txt")
    # res = Summarize.summarize_short_text(llm, text)

    # Summarize long text
    # text = file.get_as_str("LLM agents PhD thesis full.txt")
    # res = Summarize.summarize_long_text(llm, text, 15000)

    # Extract C# file code structure (homemade) 
    start_time = time.time()
    file_path = "MessageService.cs"
    code = file.get_as_str(file_path)

    # Remove existing summaries from code
    lines = code.splitlines()
    lines = [line for line in lines if not line.strip().startswith('///')]
    code = '\n'.join(lines)

    class_description: ClassDesc = CSharpCodeSplit.extract_code_struct_and_generate_methods_summaries(llm, file_path, code)

    # Generate new class file including generated summaries
    new_file_content = class_description.generate_code_with_summaries_from_initial_code(code)
    # Save file with modified code
    new_file_name = file_path.replace('.cs', '_modif.cs')
    file.write_file(new_file_content, "inputs", new_file_name)
    end_time = time.time()
    txt.display_elapsed(start_time, end_time)

    # Generate unit tests for all the class methods
    # TODO

    # class_desc_json = class_description.to_json()
    # file.write_file(class_desc_json, "outputs", file_name + ".json")



    # -- dont work --
    # retrieve fonction
    # docs = []
    # dirpath = '.\\'
    # #for dirpath, dirnames, filenames in os.walk(root_dir):
        
    #     # Go through each file
    #     #for file_name in filenames:
    # try: 
    #     # Load up the file as a doc and split
    #     current_dir = os.getcwd()
    #     loader = TextLoader(os.path.join(current_dir, "inputs\\" + file_name), encoding='utf-8')
    #     res = loader.load_and_split()
    # except Exception as e: 
    #     pass

    # for method in class_desc.methods:
    #     if method.code_chunks:
    #         for code_chunk in method.code_chunks:
    #             print(code_chunk)
    #             print("-------------------------------------------------")

def get_eur_usd_rate():
    ticker = yf.Ticker("EURUSD=X")
    data = ticker.history(period="1d")
    rate = data["Close"].iloc[-1]
    return rate

def display_tokens_consumtion(cb: OpenAICallbackHandler):
    max_len = max(len(str(cb.completion_tokens)), len(str(cb.prompt_tokens)), len(str(cb.total_tokens)))
    print(f"Prompt Tokens:       {cb.prompt_tokens}")
    print(f"Completion Tokens: + {cb.completion_tokens}")    
    print(f"                     " + "-" * max_len)
    print(f"Total Tokens:        {cb.total_tokens}")
    print(f"Cost:                {cb.total_cost / get_eur_usd_rate():.7f}€ ({cb.total_cost:.7f}$)")
    print(f"(Cost by 1K token:   {1000 * cb.total_cost / cb.total_tokens}$)")   

with get_openai_callback() as openai_callback:
    run_main()
    if llm_infos.type == LangChainAdapterType.OpenAI:
        display_tokens_consumtion(openai_callback)