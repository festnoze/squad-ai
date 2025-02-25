import json
import os
import sys
import time
from dotenv import load_dotenv
from typing import Generator
import streamlit as st
import streamlit.components.v1 as components
import markdown
from course_content_querying_service import CourseContentQueryingService
from models.course_content_models import CourseContent
from course_content_scraping_service import CourseContentScrapingService
#
from common_tools.helpers.env_helper import EnvHelper
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.helpers.file_helper import file

class ChatbotFront:
    llm = None
    parcour_composition_file_path: str = ""
    analysed_parcour_file_path: str = ""
    loaded_course_content_filename: str = ""
    previous_selected_course: str = ""
    selected_course_content_filename_wo_extension: str = ""
    loaded_course_content_md: str = ""
    loaded_course_content_html: str = ""
    parcour_content_index: int = 0
    selected_parcour_content_dir: str = ""
    parcour_courses_files: list[str] = []
    parcour_courses_files_index: int = 0
    opale_course_url: str = "https://ressources.studi.fr/contenus/opale/f5f86ccfd1194e12ef4d1e1556cc5ce83c73bbce"
    start_caption = "Bonjour, je suis StudIA, votre tuteur personnel. Comment puis-je vous aider ?"

    def run():
        ChatbotFront.init_session()
        
        st.set_page_config(
            page_title= "Extraction cours Opale Studi.com",
            page_icon= "🔎",
            layout="wide",
            initial_sidebar_state= "expanded" #"collapsed"
        )

        custom_css = """\
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .st-emotion-cache-1eo1tir {
                padding-top: 1rem !important;
                padding-bottom: 1rem !important;
            }
            .stSidebar {
                width: 502px !important;
            }
            .rounded-frame {
                border: 2px solid #3498db;
                border-radius: 15px;
                padding: 20px;
                margin-bottom: 20px;
                background-color: #f9f9f9;
            }
            .stMainBlockContainer{
                padding: 0px 30px !important;
            }
            .markdown-container {
                background-color: white;
                color: black;
                padding: 15px;
                border-radius: 5px;
                border: 1px solid #ddd;
                box-shadow: 2px 2px 10px rgba(0,0,0,0.1);
                overflow-y: auto;
                height: 400px;
                width: 100%;
            }
            .markdown-container::-webkit-scrollbar {
                width: 8px;
            }
            .markdown-container::-webkit-scrollbar-track {
                background: #f1f1f1;
            }
            .markdown-container::-webkit-scrollbar-thumb {
                background: #888;
            }
            .markdown-container::-webkit-scrollbar-thumb:hover {
                background: #555;
            }
            </style>
            """
        st.markdown(custom_css, unsafe_allow_html=True)

        focus_script = """\
            <script>
                window.onload = function() {
                    var textArea = window.parent.document.querySelector('textarea[data-testid="stChatInputTextArea"]');
                    if (textArea) {
                        textArea.focus();
                    }
                }
            </script>
            """
        components.html(focus_script, height=0)
        
        # Sidebar
        with st.sidebar:
            col1, col2 = st.columns(2) 
            with col1:
                st.button('🧽. Effacer la conversation .', on_click=ChatbotFront.start_new_conversation)                
            with col2:
                st.button("🚀. Interroger le cours  .➺", disabled=True)

            st.divider()
            st.subheader("💫 Actions disponibles :")

            with st.expander("💫 1. Analyse de la composition d'un parcours"):  
                ChatbotFront.input_folder = "inputs/"
                ChatbotFront.input_json_files = ["-"] + [f for f in os.listdir(ChatbotFront.input_folder) if f.endswith(".json")]
                ChatbotFront.parcour_composition_index = 0
                if ChatbotFront.parcour_composition_file_path in ChatbotFront.input_json_files:
                    ChatbotFront.parcour_composition_index = ChatbotFront.input_json_files.index(ChatbotFront.parcour_composition_file_path)
                ChatbotFront.parcour_composition_file_path = st.selectbox("Sélection du fichier de composition de parcours ('*.json' depuis 'inputs')", options=ChatbotFront.input_json_files, index=ChatbotFront.parcour_composition_index)
                st.button("🧪 1. Analyser la composition du parcours",  on_click=lambda: ChatbotFront.analyse_parcour_composition())   
            
            with st.expander("💫 2. Récupération du contenu de tous les cours d'un parcours"):
                ChatbotFront.output_folder = "outputs/"
                ChatbotFront.output_json_files = ["-"] + [f for f in os.listdir(ChatbotFront.output_folder) if f.endswith(".json")]
                ChatbotFront.analysed_parcour_index = 0
                if ChatbotFront.analysed_parcour_file_path in ChatbotFront.output_json_files:
                    ChatbotFront.analysed_parcour_index = ChatbotFront.output_json_files.index(ChatbotFront.analysed_parcour_file_path)
                ChatbotFront.analysed_parcour_file_path = st.selectbox("Sélection fichier d'analyse de parcours ('*.json' depuis 'outputs')", options=ChatbotFront.output_json_files, index=ChatbotFront.analysed_parcour_index)
                st.button("🔄 Récupérer des contenus de tous les cours du parcours", on_click=lambda: ChatbotFront.scrape_parcour_all_courses_opale())
           
            with st.expander("💫 3. Récupération du contenu d'un cours unique"):
                ChatbotFront.opale_course_url = st.text_input("URL du cours Opale", value=ChatbotFront.opale_course_url)
                st.button("🔄 Récupérer le cours depuis l'URL fournie", on_click=lambda: ChatbotFront.scrape_and_save_opale_course_from_url(ChatbotFront.opale_course_url))
            
            with st.expander("💫 4. Sélection du cours à interroger dans le chat", expanded=True):
                outputs_folders: list = [d for d in os.listdir("outputs/") if os.path.isdir(os.path.join("outputs/", d))]
                ChatbotFront.parcour_content_path = ["-"] + outputs_folders
                if ChatbotFront.parcour_content_index == 0 and len(ChatbotFront.parcour_content_path) >= 2:
                    ChatbotFront.parcour_content_index = 1
                if ChatbotFront.selected_parcour_content_dir in ChatbotFront.parcour_content_path:
                    ChatbotFront.parcour_content_index = ChatbotFront.parcour_content_path.index(ChatbotFront.selected_parcour_content_dir)
                ChatbotFront.selected_parcour_content_dir = st.selectbox("Sélection du parcours (dossier depuis 'outputs')", options=ChatbotFront.parcour_content_path, index=ChatbotFront.parcour_content_index)
                
                selected_parcour_path: str = "outputs/" + ChatbotFront.selected_parcour_content_dir
                if os.path.exists(selected_parcour_path):
                    ChatbotFront.parcour_courses_files = ["-"] + [f.split('.')[0] for f in os.listdir(selected_parcour_path) if os.path.isfile(os.path.join(selected_parcour_path, f)) and f.endswith(".md")]
                    if ChatbotFront.parcour_courses_files_index == 0 and len(ChatbotFront.parcour_courses_files) >= 2:
                        ChatbotFront.parcour_courses_files_index = 1
                    if ChatbotFront.loaded_course_content_filename in ChatbotFront.parcour_courses_files:
                        ChatbotFront.parcour_courses_files_index = ChatbotFront.parcour_courses_files.index(ChatbotFront.loaded_course_content_filename)
                else:
                    ChatbotFront.parcour_courses_files = ["-"]
                    ChatbotFront.parcour_courses_files_index = 0
                    ChatbotFront.loaded_course_content_filename = "-"
                
                selected_course: str = st.selectbox("Sélection fichier du cours à questionner ('*.md' depuis 'outputs/parcours')", options=ChatbotFront.parcour_courses_files, index=ChatbotFront.parcour_courses_files_index)
                
                if ChatbotFront.previous_selected_course is None or selected_course != ChatbotFront.previous_selected_course:
                    ChatbotFront.load_course_content_from_file(selected_parcour_path, selected_course)
                    ChatbotFront.previous_selected_course = selected_course
        # End of Sidebar        

        # Main window
        # Web browser
        selected_course_url = ChatbotFront.get_course_url_from_filename()
        st.components.v1.iframe(selected_course_url, height=600, scrolling=True)

        # Markdown course content display window
        #st.markdown(f'<div class="markdown-container">{ChatbotFront.loaded_course_content}</div>', unsafe_allow_html=True)
        
        # HTML course content display window
        # html_text: str = markdown.markdown(ChatbotFront.loaded_course_content_html, extensions=['fenced_code']) 
        # st.markdown(f'<div class="markdown-container">{html_text}</div>', unsafe_allow_html=True)

        # Chatbot window
        for msg in st.session_state.messages:
            st.chat_message(msg['role']).write(msg['content'])
        
        if user_query := st.chat_input(placeholder= 'Ecrivez votre question ici ...'):
            if not user_query.strip(): user_query = 'comment créer un tableau ?'
            st.chat_message('user').write_stream(ChatbotFront._write_text_as_stream(user_query))
            st.session_state.messages.append({'role': 'user', 'content': user_query})
            #st.session_state.conversation.add_new_message('user', user_query)

            with st.chat_message('assistant'):
                start = time.time()
                with st.spinner('Je réfléchis à votre question ...'):
                    # streaming_response = ChatbotFront.answer_query_stream(user_query)
                    # st.write_stream(streaming_response)
                    # full_response = streaming_response
                    full_response = ChatbotFront.answer_query_stream(user_query)
                #st.session_state.conversation.add_new_message('assistant', full_response)
                st.session_state.messages.append({'role': 'assistant', 'content': full_response})


    @staticmethod
    def start_new_conversation(): 
        st.session_state.messages = []   
        st.session_state.messages.append({'role': 'assistant', 'content': ChatbotFront.start_caption})

    @staticmethod
    def init_session():
        if 'messages' not in st.session_state:
            st.session_state['messages'] = []

    @staticmethod
    def scrape_and_save_opale_course_from_url(opale_course_url:str):
        course_content_as_pdf_url, _, _ = CourseContentScrapingService.scrape_and_save_course_content_from_url(opale_course_url)   
        st.chat_message('assistant').write(f"Le contenu du cours en PDF est extrait depuis l'adresse suivante: {course_content_as_pdf_url}")
        
    @staticmethod
    def analyse_parcour_composition() -> CourseContent:
        analysed_parcour_filename, _ = CourseContentScrapingService.analyse_parcour_composition(ChatbotFront.parcour_composition_file_path)
        
        st.chat_message('assistant').write(f'Le contenu du parcours suivant à été analysé à partir du fichier de description: "{ChatbotFront.parcour_composition_file_path}"')
        st.chat_message('assistant').write(f'Le fichier analysé à été enregistré dans les "outputs" sous le nom: "{analysed_parcour_filename}".')
        st.chat_message('assistant').write('Le nom du fichier analysé à été mis dans le champ de sélection de fichier analysé pour le scraping du contenu de tous les cours du parcours.')
        
        # Refresh the list of analysed parcours and select the newly created one
        ChatbotFront.output_json_files = ["-"] + [f for f in os.listdir(ChatbotFront.output_folder) if f.endswith(".json")]
        if not ChatbotFront.analysed_parcour_file_path in ChatbotFront.output_json_files:
            st.chat_message('assistant').write("/!\\ Le fichier d'analyse du parcours n\'a pas été trouvé dans le dossier 'outputs' /!\\")
        ChatbotFront.analysed_parcour_index = ChatbotFront.output_json_files.index(ChatbotFront.analysed_parcour_file_path)
    
    @staticmethod
    def scrape_parcour_all_courses_opale():
        course_scraping_fails_count = CourseContentScrapingService.scrape_parcour_all_courses_opale(ChatbotFront.analysed_parcour_file_path)
        st.chat_message('assistant').write(f"Le contenu de tous les cours PDF du parcours '{ChatbotFront.analysed_parcour_file_path}' ont été extraits.")
        if course_scraping_fails_count > 0:
            st.chat_message('assistant').write(f"/!\\ Echec de l'extraction pour {course_scraping_fails_count} cours. Relancer le scraping pour essayer à nouveau l'extraction.")

    def answer_query_stream(user_query: str) -> Generator[str, None, None]:
        if not ChatbotFront.loaded_course_content_md:
            st.session_state.messages.append({'role': 'assistant', 'content': "Sélectionner d'abord un cours à charger (section 4. menu à gauche)."})
            return
        
        if not ChatbotFront.llm:
            llms_infos = EnvHelper.get_llms_infos_from_env_config(skip_commented_lines=True)
            ChatbotFront.llm = LangChainFactory.create_llms_from_infos(llms_infos)[-1]
            st.session_state.messages.append({'role': 'assistant', 'content': "Modèle de langage initialisé avec succès."})
        
        answer_generator = CourseContentQueryingService.answer_user_query_on_specified_course_sync_streaming(ChatbotFront.llm, user_query, ChatbotFront.selected_parcour_content_dir, '',  ChatbotFront.loaded_course_content_md, True)
        st.write_stream(answer_generator)

    def load_course_content_from_file(course_content_path:str, selected_course_content_filename_wo_extension:str):
        if ChatbotFront.loaded_course_content_filename == selected_course_content_filename_wo_extension and ChatbotFront.loaded_course_content_md:
            st.session_state.messages.append({'role': 'assistant', 'content': f"Le contenu du cours : '{selected_course_content_filename_wo_extension}' est déjà chargé."})
            return
        
        ChatbotFront.loaded_course_content_filename = selected_course_content_filename_wo_extension
        ChatbotFront.loaded_course_content_md = CourseContentQueryingService.load_course_content_markdown(course_content_path, selected_course_content_filename_wo_extension)
        ChatbotFront.loaded_course_content_html = CourseContentQueryingService.load_course_content_html(course_content_path, selected_course_content_filename_wo_extension)

        st.session_state.messages.append({'role': 'assistant', 'content': f"Le contenu du cours : '{selected_course_content_filename_wo_extension}' a été chargé au(x) format(s) : {'MarkDown' if ChatbotFront.loaded_course_content_md else ''} {'HTML' if ChatbotFront.loaded_course_content_html else ''}."})
        st.session_state.messages.append({'role': 'assistant', 'content': 'Vous pouvez maintenant poser vos questions sur ce cours.'})

    @staticmethod
    def get_course_url_from_filename(fails_if_not_found: bool = False) -> str:
        if not os.path.exists(f'outputs/analysed_{ChatbotFront.selected_parcour_content_dir}.json'):
            if fails_if_not_found:
                raise Exception(f"Analysed parcours json file not found: '{ChatbotFront.selected_parcour_content_dir}.json' in 'outputs' folder.")
            else:
                return ""
        analysed_course_content: CourseContent = None
        with open(f'outputs/analysed_{ChatbotFront.selected_parcour_content_dir}.json', "r", encoding="utf-8") as analysed_json_file:
            loaded_analysed_json = json.load(analysed_json_file)
            analysed_course_content = CourseContent.from_dict(loaded_analysed_json)
        
        if not analysed_course_content:
            if fails_if_not_found:
                raise Exception(f"Failed to load analysed parcours from file: '{ChatbotFront.selected_parcour_content_dir}.json'")
            else:
                return ""
        for ressource in analysed_course_content.ressource_objects:
            if ressource.type == "opale":
                course_content_filename = file.build_valid_filename(ressource.name)
                if course_content_filename == ChatbotFront.loaded_course_content_filename:
                    return ressource.url
        if fails_if_not_found:
            raise Exception(f"Failed to find course: '{ChatbotFront.loaded_course_content_filename}' in analysed parcours: '{ChatbotFront.selected_parcour_content_dir}.json'")
        return ""
                
    @staticmethod
    def _write_text_as_stream(text: str, interval_btw_words:float = 0.02) -> Generator[str, None, None]:
        words = text.split(" ")
        for word in words:
            yield word + " "
            time.sleep(interval_btw_words)
        
