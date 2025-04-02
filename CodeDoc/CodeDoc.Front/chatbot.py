import os
import time
import streamlit as st
from dotenv import load_dotenv
#
from api_client import APIClient

# # common tools import
# from common_tools.helpers.txt_helper import txt
# from common_tools.models.llm_info import LlmInfo
# from common_tools.RAG.rag_inference_pipeline.rag_inference_pipeline import RagInferencePipeline
# #from common_tools.RAG.rag_inference_pipeline.rag_inference_pipeline_with_prefect import RagInferencePipelineWithPrefect
# from common_tools.RAG.rag_service import RagService
# from common_tools.RAG.rag_service_factory import RagServiceFactory
# from common_tools.helpers.rag_filtering_metadata_helper import RagFilteringMetadataHelper
# from common_tools.helpers.env_helper import EnvHelper
# # internal import
# from services.available_actions import AvailableActions

class ChatbotFront:
    ongoing_action = None
    folder_path: str = "C:/Dev/studi.*" #"C:/Dev/LMS/lms-api" #"C:/Dev/studi.api.lms.messenger/src/Studi.Api.Lms.Messenger/Controllers" #"C:/Dev/LMS/lms-api" #"C:/Dev/squad-ai/CodeSharpDoc/inputs/code_files_generated"
    files_batch_size: int = 100
    llm_batch_size: int = 100
    is_waiting: bool = False
    include_bm25_retrieval= False
    use_prefect = False

    def run():
        ChatbotFront.initialize()

        st.set_page_config(
            page_title="Chatbot DRY C#",
            page_icon="🧩",
            layout="centered",
            initial_sidebar_state="collapsed",
        )

        # Custom CSS to hide the upper right hamburger menu and footer
        hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .st-emotion-cache-1eo1tir {
                padding-top: 1rem !important;
                padding-bottom: 1rem !important;
            }
            </style>
            """
        st.markdown(hide_streamlit_style, unsafe_allow_html=True)
        
        with st.sidebar:
            st.button("🔍 Utilisez le chatbot pour Chercher du code ➺", disabled=True)
            st.button("🧽 Effacer la conversation du chatbot", on_click=ChatbotFront.clear_conversation)
            st.sidebar.markdown("---")
            st.subheader("🚀 Autres actions :")
            st.button("✨ Générer et remplacer les summary de méthodes des fichiers C# du dossier :", on_click=ChatbotFront.generate_summaries)
            ChatbotFront.folder_path = st.text_input("Dossier à traiter", value=ChatbotFront.folder_path)#, disabled=True)
            st.button("📊 Analyser structures des fichiers C#", on_click=ChatbotFront.analyse_files_code_structures)
            st.button("📦 Ajouter fichiers analysés à la base", on_click= ChatbotFront.vectorize_summaries)
            st.button("📚 Créer documentation du code C#", on_click= ChatbotFront.generate_documentations, disabled=True)

        st.title("💬 Chatbot DRY C#")
        st.markdown("<h4 style='text-align: right;'><em><strong>Réutilisez le code existant 🧩</strong></em></h4>", unsafe_allow_html=True)
        #st.caption("🚀 Générer automatiquement les commentaires de méthodes et de classes pour tout un projet C#")
        st.caption("🔍 Rechercher les fonctions existantes à partir de leur description dans tout votre codebase")
                
        if not any(st.session_state.messages):
            st.session_state.messages.append({"role": "assistant", "content": ChatbotFront.start_caption()})

        for msg in st.session_state.messages:
            st.chat_message(msg["role"]).write(msg["content"])
        
        with st.spinner("en cours d'exécution..."):
            while ChatbotFront.is_waiting == True:
                time.sleep(1)
            
        if user_query := st.chat_input():
            if not user_query.strip(): user_query = "quels sont les endpoints pour récupérer le fil d'actualité en V3 ?"
            with st.spinner("Recherche de réponses en cours ..."):
                st.session_state.messages.append({"role": "user", "content": user_query})
                st.chat_message("user").write(user_query)
                
                streaming_response = st.session_state.api_client.rag_query_stream(user_query, ChatbotFront.include_bm25_retrieval)
                st.write_stream(streaming_response)
                answer = streaming_response

                st.chat_message("assistant").write(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})

    
    # def init_session():
    #     if 'messages' not in st.session_state:            
    #         st.session_state.user = User("fake user")
    #         st.session_state['messages'] = []
    #         st.session_state['conversation'] = Conversation(st.session_state.user)
    #         st.session_state['conv_id'] = None
    #         load_dotenv()
    #         st.session_state.api_host_uri =  os.getenv("API_HOST_URI")
    #         st.session_state.api_client = APIClient(st.session_state.api_host_uri)
    #         ChatbotFront.start_new_conversation()

    def initialize():  
        if 'messages' not in st.session_state:
            st.session_state['messages'] = []

        load_dotenv()
        st.session_state.api_host_uri =  os.getenv("API_HOST_URI")
        st.session_state.api_client = APIClient(st.session_state.api_host_uri)

    @staticmethod
    def get_CodeSharpDoc_default_metadata_filters() -> dict:
        return {
                "$and": [
                    {"functional_type": "Controller"},
                    {"summary_kind": "method"}
                ]
            }

    @staticmethod    
    def clear_conversation():
        st.session_state.messages = []
        st.session_state.messages.append({"role": "assistant", "content": ChatbotFront.start_caption()})

    @staticmethod
    def start_caption():
        return "Décrivez ci-dessous la fonctionnalité que vous recherchez"
    
    @staticmethod
    def generate_summaries() -> None:
        ChatbotFront.ongoing_action = "generate_summary"
        prompt: str = f"Génération et remplacement des résumés des méthodes et classes pour tous les fichiers C# du dossier : '{ChatbotFront.folder_path}'"
        with st.spinner("En cours ... " + prompt):
            st.session_state.api_client.generate_all_summaries(ChatbotFront.files_batch_size, ChatbotFront.llm_batch_size, ChatbotFront.folder_path)
        st.session_state.messages.append({"role": "assistant", "content": "Terminé avec succès : " + prompt})

    @staticmethod
    def analyse_files_code_structures() -> None:
        ChatbotFront.ongoing_action = "analyse_files_code"
        prompt: str = f"Analyse de structure de tous les fichiers C# du dossier : '{ChatbotFront.folder_path}'"
        with st.spinner("En cours ... " + prompt):
            for folder_path in ChatbotFront.resolve_path(ChatbotFront.folder_path):
                st.session_state.api_client.analyse_files_code_structures(ChatbotFront.files_batch_size, folder_path)
        
        st.session_state.messages.append({"role": "assistant", "content": "Terminé avec succès : " + prompt})

    @staticmethod
    def resolve_path(path: str) -> list[str]:
        from glob import glob
        import os
        if not path.endswith("*"):
            return [path]
        return [f.replace('\\', '/') for f in glob(path) if os.path.isdir(f)]
    
    @staticmethod
    def vectorize_summaries() -> None:
        ChatbotFront.ongoing_action = "vectorize_summaries"
        prompt: str = "Ajout à la base vectorielle de toutes les structures analysées"
        with st.spinner("En cours ... " + prompt):
            st.session_state.api_client.rebuild_vectorstore()
        st.session_state.messages.append({"role": "assistant", "content": "Terminé avec succès : " + prompt + ". Redémarrer l'API pour recharger le vectorstore."})

    @staticmethod
    def generate_documentations() -> None:
        ChatbotFront.ongoing_action = "generate_documentation"
        prompt: str = f"En cours de génération de la documentation pour tous les fichiers C# du dossier : '{ChatbotFront.folder_path}'"
        st.session_state.messages.append({"role": "assistant", "content": prompt})
        st.chat_message("assistant").write(prompt)