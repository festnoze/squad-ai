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
from common_tools.models.langchain_adapter_type import LangChainAdapterType
from common_tools.RAG.rag_service import RAGService
from common_tools.RAG.rag_injection_pipeline.rag_injection_pipeline import RagInjectionPipeline
from common_tools.RAG.rag_inference_pipeline.rag_inference_pipeline import RagInferencePipeline
from common_tools.models.embedding_type import EmbeddingModel

class AvailableService:
    def __init__(self):
        self.out_dir = "C:/Dev/squad-ai/Chatbot-Studi.com/DataExtraction/outputs/"
        load_dotenv(find_dotenv())
        self.openai_api_key = os.getenv("OPEN_API_KEY")
        txt.activate_print = True
        llms_infos = []
        llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-4o",  timeout= 80, temperature = 0.1))
        self.rag_service = RAGService(llms_infos, EmbeddingModel.OpenAI_TextEmbedding3Small) #EmbeddingModel.Ollama_AllMiniLM


    def display_select_menu(self):
        while True:
            choice = input(dedent("""
                ┌──────────────────────────────┐
                │ DATA EXTRACTION - MAIN MENU  │
                └──────────────────────────────┘
                Tap the number of the selected action:  ① ② ③ ④
                1 - Retrieve data from Drupal json-api & Save as json files
                2 - Create a vector database after having generated and embedded documents
                3 - R Query: Retrieve similar documents (RAG w/o Augmented Generation by LLM)
                4 - RAG query: Respond with LLM augmented by similar retrieved documents
                5 - Exit
            """))
            if choice == "1":
                DrupalDataRetireval(self.out_dir)
            elif choice == "2":
                self.create_vector_db_from_generated_embeded_documents(self.out_dir)
            elif choice == "3":
                self.docs_retrieval_query()
            elif choice == "4":
                self.rag_query_console()
            elif choice == "5" or choice.lower() == "e":
                print("Exiting ...")
                exit()
                #GenerateCleanedData()

    def create_vector_db_from_generated_embeded_documents(self, out_dir):
        all_docs = GenerateDocumentsWithMetadataFromFiles().process_all_data(out_dir)
        rag_injection = RagInjectionPipeline(self.rag_service)
        txt.print_with_spinner(f"Start embedding of {len(all_docs)} documents")
        injected = rag_injection.inject_documents(all_docs, perform_chunking= False, delete_existing= True)
        txt.stop_spinner_replace_text(f"Finished Embedding on: {injected} documents")

    def docs_retrieval_query(self):
        while True:
            query = input("Entrez votre question ('exit' pour quitter):\n")
            if query == "" or query == "exit":
                return None
            self.single_docs_retrieval_query(query)

    def single_docs_retrieval_query(self, query):        
        txt.print_with_spinner("Recherche en cours ...")
        docs = self.rag_service.retrieve(query, give_score=True)
        txt.stop_spinner_replace_text(f"{len(docs)} documents trouvés")
        for doc, score in docs:
            txt.print(f"[{score:.4f}] ({doc.metadata['type']}) {doc.metadata['name']} : {doc.page_content}".strip())
        return docs
    
    def rag_query_console(self):
        inference = RagInferencePipeline(self.rag_service)
        while True:
            query = input("Entrez votre question ('exit' pour quitter):\n")
            if query == "" or query == "exit":
                return None
            response = inference.run(query, include_bm25_retrieval= True, give_score=True)
            txt.print(response)

    def rag_query(self, query):
        inference = RagInferencePipeline(self.rag_service)
        if query.startswith('!'):
            response = inference.run_static_pipeline(query[1:], include_bm25_retrieval= True, give_score=True, format_retrieved_docs_function = AvailableService.format_retrieved_docs_function)
        else:
            response = inference.run_static_pipeline(query, include_bm25_retrieval= True, give_score=True, format_retrieved_docs_function = AvailableService.format_retrieved_docs_function)
        return response

    #todo: to delete or write to add metadata to context
    @staticmethod
    def format_retrieved_docs_function(retrieved_docs):
        if not any(retrieved_docs):
            return 'not a single information were found. Don\'t answer the question.'
        return retrieved_docs
        # context = ''
        # for retrieved_doc in retrieved_docs:
        #     doc = retrieved_doc[0] if isinstance(retrieved_doc, tuple) else retrieved_doc
        #     summary = doc.page_content
        #     functional_type = doc.metadata.get('functional_type')
        #     method_name = doc.metadata.get('method_name')
        #     namespace = doc.metadata.get('namespace')
        #     struct_name = doc.metadata.get('struct_name')
        #     struct_type = doc.metadata.get('struct_type')

        #     context += f"• {summary}. In {functional_type.lower()} {struct_type.lower()}  '{struct_name}',{" method '" + method_name + "'," if method_name else ''} from namespace '{namespace}'.\n"
        return context

    def create_sqlLite_database(self, out_dir):
        db_instance = DB()
        db_instance.create_database()
        # db_instance.add_data()
        db_instance.import_data_from_json(out_dir)

if __name__ == '__main__':
    service = AvailableService()
    service.display_select_menu()