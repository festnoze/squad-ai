import re
from textwrap import dedent
from dotenv import find_dotenv, load_dotenv
import asyncio
#
from langchain.chains.query_constructor.schema import AttributeInfo
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate
#from database.database import DB
from drupal_data_retireval import DrupalDataRetireval
from generate_documents_w_metadata import GenerateDocumentsWithMetadataFromFiles
#
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.execute_helper import Execute
from common_tools.models.llm_info import LlmInfo
from common_tools.helpers.llm_helper import Llm
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.models.langchain_adapter_type import LangChainAdapterType
from common_tools.rag.rag_service import RagService
from common_tools.rag.rag_inference_pipeline.rag_pre_treatment_tasks import RAGPreTreatment
from common_tools.rag.rag_injection_pipeline.rag_injection_pipeline import RagInjectionPipeline
from common_tools.rag.rag_inference_pipeline.rag_inference_pipeline import RagInferencePipeline
from common_tools.rag.rag_inference_pipeline.rag_answer_generation_tasks import RAGAugmentedGeneration
from common_tools.helpers.ressource_helper import Ressource
#from common_tools.rag.rag_inference_pipeline.rag_inference_pipeline_with_prefect import RagInferencePipelineWithPrefect
from common_tools.models.embedding import EmbeddingModel, EmbeddingType
from common_tools.models.conversation import Conversation
from ragas_service import RagasService
from site_public_metadata_descriptions import MetadataDescriptionHelper

class AvailableService:
    inference: RagInferencePipeline = None
    rag_service: RagService = None

    def init():
        LangChainFactory.set_openai_apikey()
        use_prefect = False
        txt.activate_print = True
        AvailableService.out_dir = "C:/Dev/squad-ai/Chatbot-Studi.com/DataExtraction/outputs/"
        if not hasattr(AvailableService, 'llms_infos') or not AvailableService.llms_infos:
            AvailableService.llms_infos = []
            #AvailableService.llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "phi3", timeout= 80, temperature = 0.5))

            #AvailableService.llms_infos.append(LlmInfo(type= LangChainAdapterType.Anthropic, model= "claude-3-haiku-20240307",  timeout= 60, temperature = 0.5, api_key= anthropic_api_key))
            #AvailableService.llms_infos.append(LlmInfo(type= LangChainAdapterType.Anthropic, model= "claude-3-sonnet-20240229",  timeout= 60, temperature = 0.5, api_key= anthropic_api_key))
            #AvailableService.llms_infos.append(LlmInfo(type= LangChainAdapterType.Anthropic, model= "claude-3-opus-20240229",  timeout= 60, temperature = 0.5, api_key= anthropic_api_key))

            #AvailableService.llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo-0125",  timeout= 60, temperature = 0.5))
            #AvailableService.llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo-instruct",  timeout= 60, temperature = 0.5))
            #AvailableService.llms_infos.append(LlmInfo(type=LangChainAdapterType.OpenAI, model="gpt-4o-mini", timeout=50, temperature=0))
            AvailableService.llms_infos.append(LlmInfo(type=LangChainAdapterType.OpenAI, model="gpt-4o", timeout=80, temperature=0))
        
        if not AvailableService.rag_service:
            AvailableService.rag_service = RagService(AvailableService.llms_infos, EmbeddingModel.OpenAI_TextEmbedding3Small) #EmbeddingModel.Ollama_AllMiniLM

        if not AvailableService.inference:
            default_filters = {} #RagFilteringMetadataHelper.get_CodeSharpDoc_default_filters()
            # if use_prefect:
            #     AvailableService.inference = RagInferencePipelineWithPrefect(AvailableService.rag_service, default_filters, None)            
            # else:
            metadata_descriptions_for_studi_public_site = MetadataDescriptionHelper.get_metadata_descriptions_for_studi_public_site(AvailableService.out_dir)
            AvailableService.inference = RagInferencePipeline(AvailableService.rag_service, default_filters, metadata_descriptions_for_studi_public_site, None)
            RAGAugmentedGeneration.augmented_generation_prompt = Ressource.get_rag_augmented_generation_prompt_on_studi()

    def re_init():
        AvailableService.rag_service = None
        AvailableService.inference = None
        AvailableService.init()

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
                drupal = DrupalDataRetireval(AvailableService.out_dir)
                drupal.diplay_select_menu()
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

    def retrieve_all_data():
        drupal = DrupalDataRetireval(AvailableService.out_dir)
        drupal.retrieve_all_data()

    def create_vector_db_from_generated_embeded_documents(out_dir):
        txt.activate_print = True
        all_docs = GenerateDocumentsWithMetadataFromFiles().load_all_docs_as_json(out_dir)
        injection_pipeline = RagInjectionPipeline(AvailableService.rag_service)
        injected = injection_pipeline.build_vectorstore_and_bm25_store(all_docs, chunk_size= 2500, children_chunk_size= 0, delete_existing= True)
        AvailableService.re_init() # reload rag_service with the new vectorstore and langchain documents
        return injected

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
    #     if query.startswith('!'):
    #         response, sources = AvailableService.inference.run_pipeline_static(query[1:], include_bm25_retrieval= True, give_score=True, format_retrieved_docs_function = AvailableService.format_retrieved_docs_function)
    #     else:
    #         response, sources = AvailableService.inference.run_pipeline_dynamic(query, include_bm25_retrieval= True, give_score=True, format_retrieved_docs_function = AvailableService.format_retrieved_docs_function)
    #     return response
    
    def rag_query_with_history_streaming(conversation_history: Conversation, all_chunks_output = []):
        if conversation_history.last_message.role != 'user':
            raise ValueError("Conversation history should end with a user message")
        txt.print_with_spinner("Exécution du pipeline d'inférence ...")

        for chunk in Execute.get_sync_generator_from_async(
            AvailableService.inference.run_pipeline_dynamic_async,
            #AvailableService.inference.run_pipeline_static_async,
            conversation_history,
            include_bm25_retrieval=True,
            give_score=True,
            format_retrieved_docs_function=AvailableService.format_retrieved_docs_function,
            all_chunks_output=all_chunks_output
        ):
            # remove the stream over Http behavior: replace special '\n' and convert byte->str (as it's consumed by a UI local to the project: streamlit)
            stream_chunk = chunk.decode('utf-8').replace(Llm.new_line_for_stream_over_http, '\n')#.replace("# ", "#### ").replace("## ", "##### ").replace("### ", "###### ")
            yield stream_chunk

        txt.stop_spinner_replace_text("Pipeline d'inférence exécuté :")

    def rag_query_with_history_wo_streaming(conversation_history:Conversation):        
        txt.print_with_spinner("Execution du pipeline d'inférence ...")
        response = AvailableService.inference.run_pipeline_dynamic(conversation_history, include_bm25_retrieval= True, give_score=True, format_retrieved_docs_function = AvailableService.format_retrieved_docs_function)
        txt.stop_spinner_replace_text("Pipeline d'inférence exectué :")
        return response
    
    def summarize(text):
        promptlate = ChatPromptTemplate.from_template(dedent("""\
        # Contexte : Il s'agit de créer un résumé pour constituer la mémoire contextuelle d'un chatbot RAG.
        # Contexte métier : Il s'agit d'une réponse apportée à une demande dans le domaine de la formation en ligne sur le site Studi.com
        # Objectif : Ecrit un résumé extremement synthétique (moins de 100 mots) de la réponse suivante. 
        # Formalisme : Il s'agit de juste garder les mots clés importants du ou des éléments de réponses, ne garder que le premier niveau de réponse en cas de liste avec des sous-éléments. ne pas garder d'url. Ne pas garder les éléments de structuration. Ne pas préciser qu'il s'agit d'un résumé.
        # Texte à traiter : 
        {input}"""))
        chain = promptlate | AvailableService.rag_service.llm | RunnablePassthrough()
        result = chain.invoke(input=text)
        return Llm.get_content(result)

    def generate_ground_truth():
        #asyncio.run(RagasService.generate_ground_truth_async(AvailableService.llms_infos[0], AvailableService.rag_service.langchain_documents, 1))
        RagasService.generate_ground_truth(AvailableService.llms_infos[0], AvailableService.rag_service.langchain_documents, 1)

    #todo: to delete or write to add metadata to context
    @staticmethod
    def format_retrieved_docs_function(retrieved_docs):
        if not any(retrieved_docs):
            return 'not a single information were found. Don\'t answer the question.'
        
        total_size = sum([len(re.split(r'[ .,;:!?]', doc.page_content)) for doc in retrieved_docs])
        if total_size > 15000:
            sub_list = []
            current_size = 0            
            for doc in retrieved_docs:
                doc_size = len(re.split(r'[ .,;:!?]', doc.page_content))
                if current_size + doc_size <= 15000:
                    sub_list.append(doc)
                    current_size += doc_size
                else:
                    break            
            return sub_list
        else:
            return retrieved_docs

    # def create_sqlLite_database(out_dir):
    #     db_instance = DB()
    #     db_instance.create_database()
    #     # db_instance.add_data()
    #     db_instance.import_data_from_json(out_dir)