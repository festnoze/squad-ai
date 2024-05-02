import openai
import os
from dotenv import find_dotenv, load_dotenv
# internal import
from csharp_code_splitter import CSharpCodeSplit
from helpers.file_helper import file
from helpers.txt_helper import txt
from langchains.langchain_factory import LangChainFactory
from langchains.langchain_adapter_type import LangChainAdapterType
from models.llm_info import LlmInfo
#use cases imports
from summarize import Summarize
import json

# Load environment variables from .env file
print("Started")

load_dotenv(find_dotenv())

# Set api keys
groq_api_key = os.getenv("GROQ_API_KEY")
openai_api_key = os.getenv("OPEN_API_KEY")
openai.api_key = openai_api_key

# Select the LLM to be used
#llm_infos = LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo-0613",  timeout= 60, api_key= openai_api_key)
llm_infos = LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4-turbo-2024-04-09",  timeout= 120, api_key= openai_api_key)

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

llm = LangChainFactory.create_llm(
    adapter_type= llm_infos.type,
    llm_model_name= llm_infos.model,
    timeout_seconds= llm_infos.timeout,
    temperature= 0.1,
    api_key= llm_infos.api_key)

# Summarize short text
# text = file.get_as_str("short-text.txt")
# res = Summarize.summarize_short_text(llm, text)

# Summarize long text
# text = file.get_as_str("LLM agents PhD thesis full.txt")
# res = Summarize.summarize_long_text(llm, text, 15000)

# Extract C# file code structure
file_name = "MessageService.cs"
class_description = CSharpCodeSplit.get_code_structure(file_name)

for method in class_description.methods:
    ctor_txt = ''
    if method.is_ctor:
        ctor_txt = 'Take into account that this very method  is a constructor for the containing class of the same name.'
    text = f"Analyse method name and the method code to produce a summary of it's functionnal purpose and behavior without any mention to the method name or any technicalities. {ctor_txt} Begin by an action verb, like 'Get', 'Retrieve', 'Update', 'Check', etc ... The method name is: '{method.method_name}' and its code: {method.code} "
    method.generated_summary = Summarize.summarize_long_text(llm, text, 15000)
    print('- ' + method.generated_summary)

class_desc_json = class_description.to_json()
file.write_file(class_desc_json, "outputs", file_name + ".json")

# for method in class_desc.methods:
#     if method.code_chunks:
#         for code_chunk in method.code_chunks:
#             print(code_chunk)
#             print("-------------------------------------------------")