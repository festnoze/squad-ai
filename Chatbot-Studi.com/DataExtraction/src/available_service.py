import re
from textwrap import dedent
from dotenv import find_dotenv, load_dotenv
import asyncio
#
from langchain.chains.query_constructor.schema import AttributeInfo
#from database.database import DB
from drupal_data_retireval import DrupalDataRetireval
from generate_documents_w_metadata import GenerateDocumentsWithMetadataFromFiles
#
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.llm_helper import Llm
from common_tools.helpers.execute_helper import Execute
from common_tools.models.llm_info import LlmInfo
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
            RAGAugmentedGeneration.augmented_generation_prompt = Ressource.get_rag_augmented_generation_prompt_on_studi()

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

    def create_vector_db_from_generated_embeded_documents(out_dir):
        txt.activate_print = True
        all_docs = GenerateDocumentsWithMetadataFromFiles().load_all_docs_as_json(out_dir)
        injection_pipeline = RagInjectionPipeline(AvailableService.rag_service)
        injected = injection_pipeline.build_vectorstore_and_bm25_store(all_docs, chunk_size= 5000, children_chunk_size= 0, delete_existing= True)
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
    #     inference = RagInferencePipeline(AvailableService.rag_service)
    #     if query.startswith('!'):
    #         response, sources = inference.run_pipeline_static(query[1:], include_bm25_retrieval= True, give_score=True, format_retrieved_docs_function = AvailableService.format_retrieved_docs_function)
    #     else:
    #         response, sources = inference.run_pipeline_dynamic(query, include_bm25_retrieval= True, give_score=True, format_retrieved_docs_function = AvailableService.format_retrieved_docs_function)
    #     return response
    
    def rag_query_with_history(conversation_history: Conversation):
        txt.print_with_spinner("Chargement du pipeline d'inférence ...")
        inference = RagInferencePipeline(AvailableService.rag_service)

        if conversation_history.last_message.role != 'user':
            raise ValueError("Conversation history should end with a user message")

        # Metadata infos
        if not hasattr(RAGPreTreatment, 'metadata_infos') or not RAGPreTreatment.metadata_infos:
            RAGPreTreatment.metadata_infos = [
                AttributeInfo(name='id', description="L'identifiant interne du document courant", type='str'),
                AttributeInfo(name='type', description= dedent("""\
                    Le type de données contenu dans ce document.
                    Ajoute systématiquement un filtre sur le 'type'. Par défaut ce filtre aura la valeur : 'formation', sauf si la question parle explicitement d'un autre thème listé (comme 'métier' ou 'domaine'), 
                    Prend une valeur parmi les suivantes : ['formation', 'métier', 'certifieur', 'certification', 'diplôme', 'domaine']. 
                    Il existe aussi des valeurs spéciales : 'liste_formations' qui contient la liste de toutes les formations, et 'liste_métiers' qui contient la liste de tous les métiers.
                    Ajoute un filtre sur 'type' dès que la question traite l'un de ces sujets. 
                    Attention, n'appliquer qu'un seul filtre sur 'type' maximum. 
                    Pour le filtre : type equals 'formation', on ajoute aussi fréquement un filtre sur 'training_info_type' si on recherche des informations spécifiques sur une formation"""), type='str'),
                AttributeInfo(name='name', description="Le nom du document. Par exemple pour le filtre : type equals 'formation', il s'agit du nom de la formation", type='str'),
                AttributeInfo(name='changed', description="La date du dernier changement de la donnée", type='str'),
                AttributeInfo(name='training_info_type', description=dedent("""\
                    Spécifie le type d'informations concernant une formation.
                    Attention : ce filtre n'est valable que si : type = 'formation'. Ne pas ajouter ce filtre si le type est différent de 'formation' ! 
                    Prend une valeur parmi les suivantes (nom entre simple cotes, et description entre parenthèses) : [
                        'url' (lien vers la page web de la formation),
                        'summary' (filtre par défaut pour avoir un résumé des informations sur la formation),
                        'header-training' (informations générales sur la formation), 
                        'bref' (description en bref de la formation), 
                        'metiers' (métiers en liens avec la formation), 
                        'academic_level' (niveau académique ou niveau d'études de la formation),
                        'programme' (description du contenu détaillé de la formation), 
                        'cards-diploma' (diplômes obtenus à l'issu de la formation), 
                        'methode' (description de la méthode de l'école, rarement utile), 
                        'modalites' (les conditions d'admission, de formation, de passage des examens et autres modalités), 
                        'financement' (informations sur le tarif, le prix, et le financement et les modes de financement de la formation), 
                        'simulation' (simulation de la date de début et de la durée de formation, en cas de démarrage à la prochaine session / promotion) 
                    ]"""), type='str'),
                AttributeInfo(name='rel_ids', description="les identifiants des documents connexes au présent document", type='str')
            ]
        txt.stop_spinner_replace_text("Pipeline d'inférence chargé :")
        txt.print_with_spinner("Exécution du pipeline d'inférence ...")

        # Run the async generator directly using asyncio.run()
        for chunk in Execute.get_as_sync_stream(
            inference.run_pipeline_static_async,
            conversation_history,
            include_bm25_retrieval=True,
            give_score=True,
            format_retrieved_docs_function=AvailableService.format_retrieved_docs_function
        ):
            # remove the stream over Http behavior: replace special '\n' and convert byte->str (as it's consumed locally)
            yield chunk.decode('utf-8').replace(Llm.new_line_for_stream_over_http, '\n').replace("# ", "#### ").replace("## ", "##### ").replace("### ", "###### ")

        txt.stop_spinner_replace_text("Pipeline d'inférence exécuté :")
    
    def generate_ground_truth():
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