# internal import
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
from models.param_doc import MethodParametersDocumentation, ParameterDocumentation
from summarize import Summarize

# external imports
import openai
import os
from dotenv import find_dotenv, load_dotenv

# Text splitters
from langchain.text_splitter import CharacterTextSplitter
from langchain_community.document_loaders import TextLoader

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

# Instanciate the LLM
llm = LangChainFactory.create_llm(
    adapter_type= llm_infos.type,
    llm_model_name= llm_infos.model,
    timeout_seconds= llm_infos.timeout,
    temperature= 0.1,
    api_key= llm_infos.api_key)

# Test Groq through its own client (no langchain)
#GroqHelper.test_query(llm_infos)

# # use web search tool
# from langchain_community.utilities import GoogleSerperAPIWrapper
# web_search = GoogleSerperAPIWrapper()
# res = web_search.run("what's Obama's first name?")
# print(res)

## use tools through agent executor
#ToolsHelper.test_agent_executor_with_tools(llm)

# Summarize short text
# text = file.get_as_str("short-text.txt")
# res = Summarize.summarize_short_text(llm, text)

# Summarize long text
# text = file.get_as_str("LLM agents PhD thesis full.txt")
# res = Summarize.summarize_long_text(llm, text, 15000)

# Extract C# file code structure (homemade) 
file_name = "MessageService.cs"
class_description: ClassDesc = CSharpCodeSplit.get_code_structure(file_name)

# Generate summaries for all the class methods
for method in class_description.methods:
    ctor_txt = ''
    if method.is_ctor:
        ctor_txt = 'Take into account that this very method is a constructor for the containing class of the same name.'
    text = f"""Analyse method name and the method code to produce a summary of it's functionnal purpose and behavior without any mention to the method name or any technicalities. {ctor_txt} Begin by an action verb, like 'Get', 'Retrieve', 'Update', 'Check', etc ... The method name is: '{method.method_name}' and its code: {method.code}"""
    method_summary = Summarize.summarize_long_text(llm, text, 15000)
    method_params_str = ', '.join([item.to_str() for item in method.params])

    method_params_summaries_prompt = f"Create a description of each parameter of the following C# method. The awaited output should be a json array, with two keys: param_name, and param_desc. The list of parameters is (a parameter consist of a type followed by a name with comma as separator): '{method_params_str}'. The containing method name is: '{method.method_name}', {ctor_txt} and to help you understand the purpose of the method, method summary is: '{method_summary}'."
    #don't succeed with tools directly (for now!)
    #tools = [ParameterDocumentation.create_parameter_documentation]
    #method_params_summaries_response = ToolsHelper.invoke_llm_with_tools(llm, tools, method_params_summaries_prompt)
    method_params_summaries_response = llm.invoke(method_params_summaries_prompt)
    method_params_summaries_json = txt.get_code_block('json', txt.get_content(method_params_summaries_response))
    method_params_summaries = MethodParametersDocumentation.from_json(method_params_summaries_json)

    # method_params_prompt = f"Create a json object having each parameter name as key and each generated parameter summary as value C# method named: '{method.method_name}' having those parameters: '{method_params_str}', with this functionnal purpose: '{generated_summary}'."
    method.generated_summary = CSharpXMLDocumentation.get_xml(
        method_summary,
        method_params_summaries,
        method.return_type,
        None, #method.example
    )


# Generate new class file including generated summaries
new_file_content = class_description.generate_class_file()
# Save file with modified code
new_file_name = file_name.replace('.cs', '_modif.cs')
file.write_file(new_file_content, "inputs", new_file_name)
exit()
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