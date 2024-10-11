import time
import streamlit as st

# common tools import
from common_tools.helpers.txt_helper import txt
from common_tools.models.llm_info import LlmInfo
from common_tools.rag.rag_service import RagService
from common_tools.models.llm_info import LlmInfo

# internal import
from available_service import AvailableService

class ChatbotFront:
    ongoing_action = None
    folder_path: str = "C:/Dev/studi.api.lms.messenger/src/Studi.Api.Lms.Messenger/Controllers" #"C:/Dev/squad-ai/CodeSharpDoc/inputs/code_files_generated"
    files_batch_size: int = 100
    llm_batch_size: int = 100
    is_waiting: bool = False
    llms_infos: list[LlmInfo] = None
    rag: RagService = None
    inference_pipeline = None
    #
    include_bm25_retrieval= False
    use_prefect = False

    def main():
        services = ChatbotFront.initialize()

        st.set_page_config(
            page_title="Chatbot site public Studi.com",
            page_icon="🔎",
            layout="centered",
            initial_sidebar_state="collapsed"
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
            st.button("Utilisez le chatbot pour Rechercher  ➺", disabled=True)
            st.button("🧽 Effacer la conversation du chatbot", on_click=ChatbotFront.clear_conversation)
            st.sidebar.markdown("---")
            st.subheader("🚀 Autres actions :")
            # st.button("✨ Générer summaries des fichiers C#", on_click=ChatbotFront.generate_summaries)
            # st.button("📊 Analyser structures des fichiers C#", on_click=ChatbotFront.analyse_files_code_structures)
            # st.button("📦 Ajouter fichiers analysés à la base", on_click= ChatbotFront.vectorize_summaries)
            # st.button("📚 Créer documentation du code C#", on_click= ChatbotFront.generate_documentations, disabled=True)
            ChatbotFront.folder_path = st.text_input("Dossier à traiter", value=ChatbotFront.folder_path)#, disabled=True)

        st.title("💬 Chatbot Studi.com")
        # st.markdown("<h4 style='text-align: right;'><strong>🛰️ trouvez votre future formation</strong></h4>", unsafe_allow_html=True)
        st.caption(" Interroger notre base de connaissance sur : les métiers, nos formations, les financements, l'alternance, ...")
                
        if "messages" not in st.session_state:
            st.session_state["messages"] = []

        if not any(st.session_state.messages):
            st.session_state.messages.append({"role": "assistant", "content": ChatbotFront.start_caption()})

        for msg in st.session_state.messages:
            st.chat_message(msg["role"]).write(msg["content"])
        
        with st.spinner("en cours d'exécution..."):
            while ChatbotFront.is_waiting == True:
                time.sleep(1)
            
        custom_css = """
            <style>
            .stSpinner {
                margin-left: 20px;
            }
            </style>
        """
        st.markdown(custom_css, unsafe_allow_html=True)

        if prompt := st.chat_input(placeholder='Ecrivez votre question ici ...'):
            prompt = txt.remove_markdown(prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})
            st.chat_message("user").write(prompt)

            with st.spinner("Recherche de réponses en cours ..."):
                rag_answer = AvailableService.rag_query(prompt)
                #todo: finish it : rag_answer = AvailableService().rag_query_with_history([f"{msg['content']}" for msg in st.session_state.messages])

            rag_answer = txt.remove_markdown(rag_answer)
            st.session_state.messages.append({"role": "assistant", "content": rag_answer})
            st.chat_message("assistant").write(rag_answer)

    def initialize():
        AvailableService.init()
        
        # if not ChatbotFront.rag:
        #     ChatbotFront.rag = AvailableService.init_rag_service(ChatbotFront.llms_infos)
        # if not ChatbotFront.inference_pipeline:
        #     if ChatbotFront.use_prefect:
        #         ChatbotFront.inference_pipeline = RagInferencePipelineWithPrefect(ChatbotFront.rag, None)            
        #     else:
        #         default_filters = RagFilteringMetadataHelper.get_CodeSharpDoc_default_filters()
        #         ChatbotFront.inference_pipeline = RagInferencePipeline(ChatbotFront.rag, default_filters, None)

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
        return "Bonjour, je suis Studia, votre agent virtuel. Comment puis-je vous aider ?"

if __name__ == "__main__":
    ChatbotFront.main()