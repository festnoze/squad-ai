import os
from textwrap import dedent

from dotenv import find_dotenv, load_dotenv
from database.database import DB
from drupal_data_retireval import DrupalDataRetireval
from generate_cleaned_data import GenerateCleanedData
from generate_documents_w_metadata import GenerateDocumentsWithMetadataFromFiles
#
from common_tools.models.llm_info import LlmInfo
from common_tools.langchains.langchain_adapter_type import LangChainAdapterType
from common_tools.helpers.rag_service import RAGService
from common_tools.RAG.rag_injection_pipeline.rag_injection_pipeline import RagInjectionPipeline

class Main:
    out_dir = "C:/Dev/squad-ai/Chatbot-Studi.com/DataExtraction/outputs/"
    load_dotenv(find_dotenv())
    openai_api_key = os.getenv("OPEN_API_KEY")
    
    # db_instance = DB()
    # db_instance.create_database()
    # # db_instance.add_data()
    # db_instance.import_data_from_json(out_dir)
    # exit()
    while True:
        choice = input(dedent("""
            ┌──────────────────────────────┐
            │ DATA EXTRACTION - MAIN MENU  │
            └──────────────────────────────┘
            Tap the number of the selected action:  ① ② ③
            1 - Retrieve data from Drupal json-api & Save as json files
            2 - Generate documents with metadata from retrieved data in saved files
            3 - Generate cleaned data from retrieved ones
            4 - Exit
        """))
        if choice == "1":
            DrupalDataRetireval(out_dir)
        elif choice == "2":
            all_docs = GenerateDocumentsWithMetadataFromFiles().process_all_data(out_dir)
            llms_infos = []
            llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo-0125",  timeout= 60, temperature = 0.5, api_key= openai_api_key))
            # llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo",  timeout= 60, temperature = 0.5, api_key= openai_api_key))
            # llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4-turbo",  timeout= 120, temperature = 0.5, api_key= openai_api_key))
            # llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4o",  timeout= 80, temperature = 1, api_key= openai_api_key))
            llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4o",  timeout= 80, temperature = 0.1, api_key= openai_api_key))
            rag_service = RAGService(llms_infos)
            rag_service.build_vectorstore_from(all_docs, doChunkContent=False)
            rag_injection = RagInjectionPipeline(rag_service)
            rag_injection.inject_documents(all_docs)
        elif choice == "3":
            GenerateCleanedData()
        elif choice == "4" or choice.lower() == "e":
            print("Exiting ...")
            exit()

if __name__ == '__main__':
    Main()