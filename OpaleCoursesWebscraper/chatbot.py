import json
import os
import sys
import time
from dotenv import load_dotenv
from typing import Generator
import streamlit as st
import streamlit.components.v1 as components

from course_content_querying_service import CourseContentQueryingService
from models.course_content_models import CourseContent
from course_content_scraping_service import CourseContentScrapingService
class ChatbotFront:
    parcour_composition_file_path: str = ""
    analysed_parcour_file_path: str = ""
    loaded_course_content_filename: str = ""
    opale_course_url: str = "https://ressources.studi.fr/contenus/opale/f5f86ccfd1194e12ef4d1e1556cc5ce83c73bbce"
    start_caption = "Bonjour, je suis StudIA, votre tuteur personnel. Comment puis-je vous aider ?"

    def run():
        ChatbotFront.init_session()
        
        st.set_page_config(
            page_title= "Extraction cours Opale Studi.com",
            page_icon= "🔎",
            layout= "centered",
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
                width: 482px !important;
            }
            .rounded-frame {
                border: 2px solid #3498db;
                border-radius: 15px;
                padding: 20px;
                margin-bottom: 20px;
                background-color: #f9f9f9;
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
        
        with st.sidebar:
            st.button("🚀 Interroger le cours à droite ➺", disabled=True)
            st.button('🧽 Effacer la conversation du chatbot', on_click=ChatbotFront.start_new_conversation)
            st.divider()

            st.subheader("💫 Gestion du contenu d'un parcours")         
            #ChatbotFront.parcour_composition_file_path = st.text_input("Fichier de composition du parcours ('*.json' depuis 'inputs')", value=ChatbotFront.parcour_composition_file_path)
            ChatbotFront.input_folder = "inputs/"
            ChatbotFront.input_json_files = ["-"] + [f for f in os.listdir(ChatbotFront.input_folder) if f.endswith(".json")]
            ChatbotFront.parcour_composition_index = 0
            if ChatbotFront.parcour_composition_file_path in ChatbotFront.input_json_files:
                ChatbotFront.parcour_composition_index = ChatbotFront.input_json_files.index(ChatbotFront.parcour_composition_file_path)
            
            ChatbotFront.parcour_composition_file_path = st.selectbox("Sélection fichier de composition du parcours ('*.json' depuis 'inputs')", options=ChatbotFront.input_json_files, index=ChatbotFront.parcour_composition_index)
            
            st.button("🧪 1. Analyser la composition du parcours",  on_click=lambda: ChatbotFront.analyse_parcour_composition())   
            
            st.divider()
            
            #st.subheader("💫 Récupération du contenu de tous les cours d'un parcours")
            #ChatbotFront.analysed_course_file_path = st.text_input("Fichier d'analyse du parcours ('*.json' depuis 'ouputs')", value=ChatbotFront.analysed_course_file_path)
            ChatbotFront.output_folder = "outputs/"
            ChatbotFront.output_json_files = ["-"] + [f for f in os.listdir(ChatbotFront.output_folder) if f.endswith(".json")]
            ChatbotFront.analysed_parcour_index = 0
            if ChatbotFront.analysed_parcour_file_path in ChatbotFront.output_json_files:
                ChatbotFront.analysed_parcour_index = ChatbotFront.output_json_files.index(ChatbotFront.analysed_parcour_file_path)

            ChatbotFront.analysed_parcour_file_path = st.selectbox("Sélection fichier d'analyse de parcours ('*.json' depuis 'outputs')", options=ChatbotFront.output_json_files, index=ChatbotFront.analysed_parcour_index)
 
            st.button("🔄 2. Récupérer le contenu de TOUS les cours du parcours", on_click=lambda: ChatbotFront.scrape_parcour_all_courses_opale())
           
            st.divider()

            st.subheader("💫 Récupération du contenu d'un cours unique")
            ChatbotFront.opale_course_url = st.text_input("URL du cours Opale", value=ChatbotFront.opale_course_url)
            st.button("🔄 Récupérer le cours depuis l'URL fournie", on_click=lambda: ChatbotFront.scrape_and_save_opale_course_from_url(ChatbotFront.opale_course_url))
            
            st.divider()
            
            st.subheader("💫 Sélection du cours à interroger dans le chat")
            outputs_folders = [d for d in os.listdir("outputs/") if os.path.isdir(os.path.join("outputs/", d))]
            ChatbotFront.parcour_content_path = ["-"] + outputs_folders
            ChatbotFront.selected_parcour_content_dir = st.selectbox("Sélection du parcours (dossier depuis 'outputs')", options=ChatbotFront.parcour_content_path, index=ChatbotFront.analysed_parcour_index)
 
            selected_parcour_path = "outputs/" + ChatbotFront.selected_parcour_content_dir
            if os.path.exists(selected_parcour_path):
                ChatbotFront.parcour_courses_files = ["-"] + [f for f in os.listdir(selected_parcour_path) if os.path.isfile(os.path.join(selected_parcour_path, f)) and f.endswith(".md")]
                ChatbotFront.parcour_courses_files_index = 0
                if ChatbotFront.loaded_course_content_filename in ChatbotFront.parcour_courses_files:
                    ChatbotFront.parcour_courses_files_index = ChatbotFront.output_json_files.index(ChatbotFront.loaded_course_content_filename)
            else:
                ChatbotFront.parcour_courses_files = ["-"]
                ChatbotFront.parcour_courses_files_index = 0
                ChatbotFront.loaded_course_content_filename = "-"
            ChatbotFront.new_loaded_course_content_filename = st.selectbox("Sélection fichier du cours à questionner ('*.md' depuis 'outputs/parcours')", options=ChatbotFront.parcour_courses_files, index=ChatbotFront.parcour_courses_files_index)
            if ChatbotFront.new_loaded_course_content_filename != ChatbotFront.loaded_course_content_filename:
                ChatbotFront.loaded_course_content_filename = ChatbotFront.new_loaded_course_content_filename
                ChatbotFront.load_course_content_from_file(selected_parcour_path + "/" + ChatbotFront.loaded_course_content_filename)
            st.button("🔄 Sélectionner ce cours à questionner", on_click=lambda: ChatbotFront.select_course_to_query(ChatbotFront.course_content_file_path))
            
            
            # st.subheader("💫 Evaluation du pipeline d'inference")
            # st.button('✨ Générer RAGAS Ground Truth dataset',      on_click=lambda: st.session_state.api_client.generate_ground_truth())

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
                    streaming_response = answer_query_stream(user_query)
                    st.write_stream(streaming_response)
                    full_response = streaming_response
                    
                #st.session_state.conversation.add_new_message('assistant', full_response)
                st.session_state.messages.append({'role': 'assistant', 'content': full_response})


    def start_new_conversation(): 
        st.session_state.messages = []   
        st.session_state.messages.append({'role': 'assistant', 'content': ChatbotFront.start_caption})

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
        st.chat_message('assistant').write(f"Le contenu de tous les cours PDF du parcours: {ChatbotFront.parcour_composition_file_path} ont été extraits.")
        if course_scraping_fails_count > 0:
            st.chat_message('assistant').write(f"Nombre de cours non extraits: {course_scraping_fails_count}. Relancer le scraping du parcours pour les extraire.")

    def answer_query_stream(user_query: str) -> Generator[str, None, None]:
        answer = CourseContentQueryingService.answer_user_query_on_specified_course(user_query, ChatbotFront.opale_course_url)


    def select_course_to_query(course_content_file_path:str):
        st.chat_message('assistant').write(f"Le cours suivant à été sélectionné pour être questionné: {course_content_file_path}")
        st.chat_message('assistant').write('Vous pouvez maintenant poser vos questions sur ce cours.')

    def load_course_content_from_file(course_content_file_path:str):
        ChatbotFront.course_content = CourseContentQueryingService.load_course_content(course_content_file_path)
        st.chat_message('assistant').write(f"Le cours suivant à été chargé pour être questionné: {course_content_file_path}")
        st.chat_message('assistant').write('Vous pouvez maintenant poser vos questions sur ce cours.')
        
