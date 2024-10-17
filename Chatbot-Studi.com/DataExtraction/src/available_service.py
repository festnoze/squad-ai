from textwrap import dedent
from dotenv import find_dotenv, load_dotenv
#
from langchain.chains.query_constructor.schema import AttributeInfo
#from database.database import DB
from drupal_data_retireval import DrupalDataRetireval
from generate_documents_w_metadata import GenerateDocumentsWithMetadataFromFiles
from common_tools.rag.rag_inference_pipeline.rag_pre_treatment_tasks import RAGPreTreatment
#
from common_tools.helpers import txt
from common_tools.models.llm_info import LlmInfo
from common_tools.models.langchain_adapter_type import LangChainAdapterType
from common_tools.rag.rag_service import RagService
from common_tools.rag.rag_injection_pipeline.rag_injection_pipeline import RagInjectionPipeline
from common_tools.rag.rag_inference_pipeline.rag_inference_pipeline import RagInferencePipeline
#from common_tools.rag.rag_inference_pipeline.rag_inference_pipeline_with_prefect import RagInferencePipelineWithPrefect
from common_tools.models.embedding import EmbeddingModel, EmbeddingType
from common_tools.models.conversation import Conversation
from ragas_service import RagasService

class AvailableService:
    def init():
        use_prefect = False
        txt.activate_print = True
        AvailableService.out_dir = "C:/Dev/squad-ai/Chatbot-Studi.com/DataExtraction/outputs/"
        if not hasattr(AvailableService, 'llms_infos') or not AvailableService.llms_infos:
            AvailableService.llms_infos = []
            #AvailableService.llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "phi3", timeout= 80, temperature = 0.5))
            #AvailableService.llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo-0125",  timeout= 60, temperature = 0.5))
            #AvailableService.llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo-instruct",  timeout= 60, temperature = 0.5))
            AvailableService.llms_infos.append(LlmInfo(type=LangChainAdapterType.OpenAI, model="gpt-4o-mini", timeout=50, temperature=0))
            #AvailableService.llms_infos.append(LlmInfo(type=LangChainAdapterType.OpenAI, model="gpt-4o", timeout=80, temperature=0))
        
        if not hasattr(AvailableService, 'rag_service') or not AvailableService.rag_service:
            AvailableService.rag_service = RagService(AvailableService.llms_infos, EmbeddingModel.OpenAI_TextEmbedding3Small) #EmbeddingModel.Ollama_AllMiniLM

        if not hasattr(AvailableService, 'inference') or not AvailableService.inference:
            default_filters = {} #RagFilteringMetadataHelper.get_CodeSharpDoc_default_filters()
            # if use_prefect:
            #     AvailableService.inference = RagInferencePipelineWithPrefect(AvailableService.rag_service, default_filters, None)            
            # else:
            AvailableService.inference = RagInferencePipeline(AvailableService.rag_service, default_filters, None)

    def display_select_menu():
        while True:
            choice = input(dedent("""
                ┌──────────────────────────────┐
                │ DATA EXTRACTION - MAIN MENU  │
                └──────────────────────────────┘
                Tap the number of the selected action:  ① ② ③ ④
                1 - Retrieve data from Drupal json-api & Save as json files
                2 - Create a vector database after having generated and embedded documents
                3 - R Query: Retrieve similar documents (rag w/o Augmented Generation by LLM)
                4 - rag query: Respond with LLM augmented by similar retrieved documents
                5 - Exit
            """))
            if choice == "1":
                DrupalDataRetireval(AvailableService.out_dir)
            elif choice == "2":
                AvailableService.create_vector_db_from_generated_embeded_documents(AvailableService.out_dir)
            elif choice == "3":
                AvailableService.docs_retrieval_query()
            elif choice == "4":
                AvailableService.rag_query_console()
            elif choice == "5" or choice.lower() == "e":
                print("Exiting ...")
                exit()
                #GenerateCleanedData()

    def create_vector_db_from_generated_embeded_documents(out_dir):
        all_docs = GenerateDocumentsWithMetadataFromFiles().load_all_docs_as_json(out_dir)
        rag_injection = RagInjectionPipeline(AvailableService.rag_service)
        txt.print_with_spinner(f"Start embedding of {len(all_docs)} documents")
        injected = rag_injection.inject_documents(all_docs, perform_chunking= False, delete_existing= True)
        txt.stop_spinner_replace_text(f"Finished Embedding on: {injected} documents")

    def docs_retrieval_query():
        while True:
            query = input("Entrez votre question ('exit' pour quitter):\n")
            if query == "" or query == "exit":
                return None
            AvailableService.single_docs_retrieval_query(query)

    def single_docs_retrieval_query(query):        
        txt.print_with_spinner("Recherche en cours ...")
        docs = AvailableService.rag_service.semantic_vector_retrieval(query, give_score=True)
        txt.stop_spinner_replace_text(f"{len(docs)} documents trouvés")
        for doc, score in docs:
            txt.print(f"[{score:.4f}] ({doc.metadata['type']}) {doc.metadata['name']} : {doc.page_content}".strip())
        return docs
    
    def rag_query_console():        
        while True:
            query = input("Entrez votre question ('exit' pour quitter):\n")
            if query == "" or query == "exit":
                return None
            response, sources = AvailableService.inference.run(query, include_bm25_retrieval= True, give_score=True)
            txt.print(response)

    # def rag_query_wo_history(query):
    #     inference = RagInferencePipeline(AvailableService.rag_service)
    #     if query.startswith('!'):
    #         response, sources = inference.run_pipeline_static(query[1:], include_bm25_retrieval= True, give_score=True, format_retrieved_docs_function = AvailableService.format_retrieved_docs_function)
    #     else:
    #         response, sources = inference.run_pipeline_dynamic(query, include_bm25_retrieval= True, give_score=True, format_retrieved_docs_function = AvailableService.format_retrieved_docs_function)
    #     return response
    
    async def rag_query_with_history_async(conversation_history:Conversation):
        txt.print_with_spinner("Chargement du pipeline d'inférence ...")
        inference = RagInferencePipeline(AvailableService.rag_service)
        if conversation_history.last_message.role != 'user':
            raise ValueError("Conversation history should end with a user message")
        
        # Set static metadata infos to avoid extra calculation
        RAGPreTreatment.metadata_infos = [
            AttributeInfo(name='id', description="l'identifiant interne du document courant", type='str'),
            AttributeInfo(name='type', description="le type de données contenu dans ce document. Il s'agit d'une valeur parmi les catégories suivantes: ['certifieur', 'certification', 'diplôme', 'domaine', 'financement', 'métier', 'formation']. Les plus fréquements concernées sont : métier et formation, ajout ce filtre dès que la question à trait à l'un de ces sujets", type='str'),
            AttributeInfo(name='name', description="le nom du sujet du document", type='str'),
            AttributeInfo(name='changed', description="'la date de dernier changement de la donnée", type='str'),
            AttributeInfo(name='rel_ids', description="les identifiants des documents connexes au présent document", type='str')
        ]
        
        txt.stop_spinner_replace_text("Pipeline d'inférence chargé :")
        
        txt.print_with_spinner("Execution du pipeline d'inférence ...")
        async for chunk in inference.run_pipeline_static(conversation_history, include_bm25_retrieval= True, give_score=True, format_retrieved_docs_function = AvailableService.format_retrieved_docs_function):
            yield chunk
        txt.stop_spinner_replace_text("Pipeline d'inférence exectué :")
    
    def generate_ground_truth():
        RagasService.generate_ground_truth(AvailableService.llms_infos[0], AvailableService.rag_service.langchain_documents, 1)

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
        # return context

    # def create_sqlLite_database(out_dir):
    #     db_instance = DB()
    #     db_instance.create_database()
    #     # db_instance.add_data()
    #     db_instance.import_data_from_json(out_dir)