import os
from textwrap import dedent

from dotenv import find_dotenv, load_dotenv
from database.database import DB
from drupal_data_retireval import DrupalDataRetireval
from generate_cleaned_data import GenerateCleanedData
from generate_documents_w_metadata import GenerateDocumentsWithMetadataFromFiles
#
from common_tools.helpers import txt
from common_tools.models.llm_info import LlmInfo
from common_tools.langchains.langchain_adapter_type import LangChainAdapterType
from common_tools.RAG.rag_service import RAGService
from common_tools.RAG.rag_injection_pipeline.rag_injection_pipeline import RagInjectionPipeline

class Main:
    def __init__(self):
        self.out_dir = "C:/Dev/squad-ai/Chatbot-Studi.com/DataExtraction/outputs/"
        load_dotenv(find_dotenv())
        self.openai_api_key = os.getenv("OPEN_API_KEY")
        txt.activate_print = True
        llms_infos = []
        llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4o",  timeout= 80, temperature = 0.1, api_key= self.openai_api_key))
        self.rag_service = RAGService(llms_infos)
        self.display_select_menu()

    def display_select_menu(self):
        while True:
            choice = input(dedent("""
                ┌──────────────────────────────┐
                │ DATA EXTRACTION - MAIN MENU  │
                └──────────────────────────────┘
                Tap the number of the selected action:  ① ② ③ ④
                1 - Retrieve data from Drupal json-api & Save as json files
                2 - Generate documents with metadata from retrieved data in saved files
                3 - RAG query  
                4 - Exit
            """))
            if choice == "1":
                DrupalDataRetireval(self.out_dir)
            elif choice == "2":
                self.create_vector_db_from_generated_embeded_documents(self.out_dir)
            elif choice == "3":
                #GenerateCleanedData()
                self.rag_query()
            elif choice == "4" or choice.lower() == "e":
                print("Exiting ...")
                exit()

    def create_vector_db_from_generated_embeded_documents(self, out_dir):
        all_docs = GenerateDocumentsWithMetadataFromFiles().process_all_data(out_dir)
        rag_injection = RagInjectionPipeline(self.rag_service)
        txt.print_with_spinner(f"Start embedding of {len(all_docs)} documents")
        injected = rag_injection.inject_documents(all_docs, doChunkContent= False)
        txt.stop_spinner_replace_text(f"Finished Embedding on: {injected} documents")

    def rag_query(self):
        while True:
            query = input("Entrez votre question ('exit' pour quitter):\n")
            if query == "" or query == "exit":
                return
            docs = self.rag_service.retrieve(query, give_score=True)
            for doc, score in docs:
                print(f"({doc.metadata['type']}) {doc.metadata['name']} : {doc.page_content}".strip() + f" - score: {score}")

    def create_sqlLite_database(self, out_dir):
        db_instance = DB()
        db_instance.create_database()
        # db_instance.add_data()
        db_instance.import_data_from_json(out_dir)

if __name__ == '__main__':
    Main()