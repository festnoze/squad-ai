import time
from openai import OpenAI
import streamlit as st
# common tools import
from common_tools.helpers.txt_helper import txt
from common_tools.models.llm_info import LlmInfo
from common_tools.RAG.rag_inference_pipeline.rag_inference_pipeline import RagInferencePipeline
from common_tools.RAG.rag_inference_pipeline.rag_inference_pipeline_with_prefect import RagInferencePipelineWithPrefect
from common_tools.helpers.rag_service import RAGService
# internal import
from services.available_actions import AvailableActions
from startup import Startup

class ChatbotFront:
    ongoing_action = None
    folder_path: str = "C:/Dev/studi.api.lms.messenger/src/Studi.Api.Lms.Messenger/Controllers" #"C:/Dev/squad-ai/CodeSharpDoc/inputs/code_files_generated"
    files_batch_size: int = 100
    llm_batch_size: int = 100
    is_waiting: bool = False
    llms_infos: list[LlmInfo] = None
    rag: RAGService = None
    inference_pipeline = None
    #
    include_bm25_retrieval= False
    use_prefect = False

    def main():
        ChatbotFront.initialize()

        st.set_page_config(
            page_title="DRY C# Chatbot",
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
            st.button("🔍 Utilisez le chatbot pour Rechercher  ➺", disabled=True)
            st.button("🧽 Effacer la conversation du chatbot", on_click=ChatbotFront.clear_conversation)
            st.sidebar.markdown("---")
            st.subheader("🚀 Autres actions :")
            st.button("✨ Générer summaries des fichiers C#", on_click=ChatbotFront.generate_summaries)
            st.button("📊 Analyser structures des fichiers C#", on_click=ChatbotFront.analyse_files_code_structures)
            st.button("📦 Ajouter fichiers analysés à la base", on_click= ChatbotFront.vectorize_summaries)
            st.button("📚 Créer documentation du code C#", on_click= ChatbotFront.generate_documentations, disabled=True)
            ChatbotFront.folder_path = st.text_input("Dossier à traiter", value=ChatbotFront.folder_path)#, disabled=True)

        st.title("💬 Chatbot DRY C#")
        st.markdown("<h4 style='text-align: right;'><em><strong>Réutilisez le code existant 🧩</strong></em></h4>", unsafe_allow_html=True)
        #st.caption("🚀 Générer automatiquement les commentaires de méthodes et de classes pour tout un projet C#")
        st.caption("🔍 Rechercher les fonctions existantes à partir de leur description dans tout votre codebase")
                
        if "messages" not in st.session_state:
            st.session_state["messages"] = []

        if not any(st.session_state.messages):
            st.session_state.messages.append({"role": "assistant", "content": ChatbotFront.start_caption()})

        for msg in st.session_state.messages:
            st.chat_message(msg["role"]).write(msg["content"])
        
        with st.spinner("en cours d'exécution..."):
            while ChatbotFront.is_waiting == True:
                time.sleep(1)
            
        if prompt := st.chat_input():
            with st.spinner("Recherche de réponses en cours ..."):
                st.session_state.messages.append({"role": "user", "content": txt.remove_markdown(prompt)})
                st.chat_message("user").write(prompt)
                AvailableActions.rag_querying_from_sl_chatbot(ChatbotFront.inference_pipeline, prompt, st, ChatbotFront.include_bm25_retrieval)

    def initialize():
        txt.activate_print = True
        if not ChatbotFront.llms_infos:
            ChatbotFront.llms_infos = Startup.initialize()
        if not ChatbotFront.rag:
            ChatbotFront.rag = AvailableActions.init_rag_service(ChatbotFront.llms_infos)
        if not ChatbotFront.inference_pipeline:
            if ChatbotFront.use_prefect:
                ChatbotFront.inference_pipeline = RagInferencePipelineWithPrefect(ChatbotFront.rag, None)            
            else:
                ChatbotFront.inference_pipeline = RagInferencePipeline(ChatbotFront.rag, None)

    def clear_conversation():
        st.session_state.messages = []
        st.session_state.messages.append({"role": "assistant", "content": ChatbotFront.start_caption()})

    def generate_summaries():
        ChatbotFront.ongoing_action = "generate_summary"
        prompt = f"Génération et remplacement des résumés des méthodes et classes pour tous les fichiers C# du dossier : '{ChatbotFront.folder_path}'"
        with st.spinner("En cours ... " + prompt):
            AvailableActions.generate_all_summaries(ChatbotFront.llms_infos, ChatbotFront.files_batch_size, ChatbotFront.llm_batch_size, ChatbotFront.folder_path)
        st.session_state.messages.append({"role": "assistant", "content": txt.remove_markdown("Terminé avec succès : " + prompt)})

    def analyse_files_code_structures():
        ChatbotFront.ongoing_action = "analyse_files_code"
        prompt = f"Analyse de structure de tous les fichiers C# du dossier : '{ChatbotFront.folder_path}'"
        with st.spinner("En cours ... " + prompt):
            AvailableActions.analyse_files_code_structures(ChatbotFront.files_batch_size, ChatbotFront.folder_path)
        st.session_state.messages.append({"role": "assistant", "content": txt.remove_markdown("Terminé avec succès : " + prompt)})

    def vectorize_summaries():
        ChatbotFront.ongoing_action = "vectorize_summaries"
        prompt = f"Ajout à la base vectorielle de toutes les structures analysées"
        with st.spinner("En cours ... " + prompt):
            AvailableActions.rebuild_vectorstore(ChatbotFront.llms_infos)
        st.session_state.messages.append({"role": "assistant", "content": txt.remove_markdown("Terminé avec succès : " + prompt)})

    def generate_documentations():
        ChatbotFront.ongoing_action = "generate_documentation"
        prompt = f"En cours de génération de la documentation pour tous les fichiers C# du dossier : '{ChatbotFront.folder_path}'"
        st.session_state.messages.append({"role": "assistant", "content": txt.remove_markdown(prompt)})
        st.chat_message("assistant").write(prompt)

    def start_caption():
        return "Décrivez ci-dessous la fonctionnalité que vous recherchez"

if __name__ == "__main__":
    ChatbotFront.main()