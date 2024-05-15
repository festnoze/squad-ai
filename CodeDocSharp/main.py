# internal import
import time
from csharp_code_parser import CSharpCodeStructureParser
from helpers.file_helper import file
from helpers.llm_helper import Llm
from helpers.test_helpers import test_agent_executor_with_tools, test_parallel_chains_invocations_with_imputs, test_parallel_invocations_with_homemade_parallel_chains_invocations, test_parallel_invocations_with_homemade_parallel_prompts_invocations
from helpers.txt_helper import txt
from langchains.langchain_factory import LangChainFactory
from langchains.langchain_adapter_type import LangChainAdapterType
from models.class_desc import ClassDesc
from models.llm_info import LlmInfo
from summarize import Summarize
from helpers.groq_helper import GroqHelper

# external imports
import openai
import os
from dotenv import find_dotenv, load_dotenv

# Text splitters
from langchain.text_splitter import CharacterTextSplitter
from langchain_community.document_loaders import TextLoader
from langchain_community.callbacks import get_openai_callback, OpenAICallbackHandler

# Load environment variables from .env file
print("Started")

load_dotenv(find_dotenv())

# Set api keys
groq_api_key = os.getenv("GROQ_API_KEY")
openai_api_key = os.getenv("OPEN_API_KEY")
openai.api_key = openai_api_key

# models = openai.models.list()
# for model in models:
#     print(model.id)
# exit()

def generate_csharp_files_summaries(file_path: str, file_name: str, llm_infos: LlmInfo):
    # Instanciate the LLM
    llm = LangChainFactory.create_llm(
        adapter_type= llm_infos.type,
        llm_model_name= llm_infos.model,
        timeout_seconds= llm_infos.timeout,
        temperature= 1.0,
        api_key= llm_infos.api_key)
    
    # Load C# file code
    start_time = time.time()
    if file_path and file_name:   
        full_file_path = os.path.join(file_path, file_name)
    else:
        if file_path:
            full_file_path = file_path
        else:
            full_file_path = file_name            
    code = file.get_as_str(full_file_path)

    # Remove existing summaries from code
    lines = code.splitlines()
    lines = [line for line in lines if not line.strip().startswith('///')]
    code = '\n'.join(lines)

    # Extract code structure from C# file
    class_description: ClassDesc = CSharpCodeStructureParser.extract_code_struct(llm, file_path, code)
    
    # Generate summaries for all methods for the current class
    CSharpCodeStructureParser.generate_all_methods_summaries(llm, class_description, True)

    # Including generated summaries to class code
    new_code = class_description.generate_code_with_summaries_from_initial_code(code)

    # Save file with modified code
    new_file_name = full_file_path.replace('.cs', '_modif.cs')
    file.write_file(new_code, "inputs", new_file_name)
    end_time = time.time()
    txt.display_elapsed(start_time, end_time)

def invoke_method_mesuring_tokens_consumption(method_handler, *args, **kwargs):
    """
    Invokes the provided method handler within an OpenAI callback context 
    and displays the token consumption.
    
    Args:
        method_handler (callable): The method to be executed.
        *args: Variable length argument list for the method_handler.
        **kwargs: Arbitrary keyword arguments for the method_handler.
    """
    with get_openai_callback() as openai_callback:
        method_handler(*args, **kwargs)
        Llm.display_tokens_consumtion(openai_callback)


# Select the LLM to be used
#llm_infos = LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo-0613",  timeout= 60, api_key= openai_api_key)
#llm_infos = LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4-turbo-2024-04-09",  timeout= 120, api_key= openai_api_key)
llm_infos = LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4o",  timeout= 60, api_key= openai_api_key)

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

invoke_method_mesuring_tokens_consumption(generate_csharp_files_summaries, None, "MessageService.cs", llm_infos)