import json
import os
import sys
import time
from dotenv import load_dotenv
from typing import Generator
import streamlit as st
import streamlit.components.v1 as components

from course_content_models import CourseContent
class ChatbotFront:
    course_file_path: str = "bachelor-developpeur-python.json"#"api-v3-courses-parcours.json"
    url: str = "https://ressources.studi.fr/contenus/opale/f5f86ccfd1194e12ef4d1e1556cc5ce83c73bbce"

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
                width: 362px !important;
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

            st.subheader("💫 Scraption des cours")
            
            ChatbotFront.course_file_path = st.text_input("Json dans dossier 'inputs' du contenu de parcours", value=ChatbotFront.course_file_path)
            st.button("🧪 Analyser le contenu du parcours",   on_click=lambda: ChatbotFront.parse_course_content())
            ChatbotFront.url = st.text_input("URL du cours Opale", value=ChatbotFront.url)
            st.button("🔄 Récupérer le cours depuis l'URL fournie", on_click=lambda: ChatbotFront.scrape_url_for_opale_course())
            # st.button("🧪 Tester tous les modèles d'inférence",   on_click=lambda: ChatbotFront.test_all_inference_models())
            # st.button('📥 Récupérer données Drupal par json-api',   on_click=lambda: st.session_state.api_client.retrieve_all_data())
            # st.button('🌐 Scraping des pages web des formations',   on_click=lambda: st.session_state.api_client.scrape_website_pages())
            # st.button('🗂️ Construction de la base vectorielle',     on_click=lambda: st.session_state.api_client.build_vectorstore())
            # st.button('🗃️ Construction base vectorielle synthétique + questions', on_click=lambda: st.session_state.api_client.build_summary_vectorstore())
            st.divider()
            
            # st.subheader("💫 Evaluation du pipeline d'inference")
            # st.button('✨ Générer RAGAS Ground Truth dataset',      on_click=lambda: st.session_state.api_client.generate_ground_truth())

        for msg in st.session_state.messages:
            st.chat_message(msg['role']).write(msg['content'])
        
        if user_query := st.chat_input(placeholder= 'Ecrivez votre question ici ...'):
            if not user_query.strip(): user_query = 'quels bts en rh ?'
            st.chat_message('user').write_stream(ChatbotFront._write_text_as_stream(user_query))
            st.session_state.messages.append({'role': 'user', 'content': user_query})
            st.session_state.conversation.add_new_message('user', user_query)

            with st.chat_message('assistant'):
                start = time.time()
                # with st.spinner('Je réfléchis à votre question ...'):
                #     request_model = UserQueryAskingRequestModel(conversation_id=st.session_state.conv_id, user_query_content=user_query)
                #     streaming_response = st.session_state.api_client.rag_query_stream(request_model)
                #     st.write_stream(streaming_response)
                #     full_response = streaming_response
                    
                # st.session_state.conversation.add_new_message('assistant', full_response)
                # st.session_state.messages.append({'role': 'assistant', 'content': full_response})


    def start_new_conversation(): 
        st.session_state.messages = []        
        # st.session_state.conversation = Conversation(st.session_state.user)
        # st.session_state.conversation.add_new_message('assistant', ChatbotFront._start_caption())
        # st.session_state.messages.append({
        #                     'role': st.session_state.conversation.last_message.role, 
        #                     'content': st.session_state.conversation.last_message.content})
        # # Inform the API
        # st.session_state.user_id = st.session_state.api_client.create_or_update_user(UserRequestModel(user_id=None, user_name=st.session_state.user.name))
        # st.session_state.conv_id = st.session_state.api_client.create_new_conversation(st.session_state.user_id)

    def init_session():
        if 'messages' not in st.session_state:
            st.session_state['messages'] = []
            # st.session_state['conversation'] = Conversation(st.session_state.user)
            # st.session_state['conv_id'] = None
            # load_dotenv()
            # st.session_state.api_host_uri =  os.getenv("API_HOST_URI")
            # ChatbotFront.start_new_conversation()

    def scrape_url_for_opale_course(ressource_name:str = "pdf_document", relative_path:str = "outputs/"):
        from generic_web_scraper import GenericWebScraper
        use_selenium = True
        scraper = GenericWebScraper()
        content_url = scraper.extract_single_href_from_url(ChatbotFront.url, "Commencer le cours", use_selenium=use_selenium)
        st.chat_message('assistant').write(f"Le contenu du cours est disponible à l'adresse suivante: {content_url}")
        #
        pdf_url = scraper.extract_single_href_from_url(content_url, "Imprimer", use_selenium=use_selenium)
        course_content_text, course_content_html  = scraper.get_pdf_as_markdown_from_url(pdf_url)
        
        st.chat_message('assistant').write(f"Le contenu du cours en PDF est disponible à l'adresse suivante: {pdf_url}")

        with open(f"{relative_path}{ressource_name}.md", "w", encoding="utf-8") as text_file:
            text_file.write(course_content_text)
        with open(f"{relative_path}{ressource_name}.html", "w", encoding="utf-8") as html_file:
            html_file.write(course_content_html)

    @staticmethod
    def _start_caption():
        return "Bonjour, je suis StudIA, votre tuteur personnel. Comment puis-je vous aider ?"

    @staticmethod
    def parse_course_content(save_parsed_course: bool = True, load_parsed_course_instead_if_exist: bool = True) -> CourseContent:
        if load_parsed_course_instead_if_exist and os.path.exists('outputs/analysed_' + ChatbotFront.course_file_path):
            with open('outputs/analysed_' + ChatbotFront.course_file_path, "r", encoding="utf-8") as read_json_file:
                loaded_data = json.load(read_json_file)
                course_content = CourseContent.from_dict(loaded_data)
        else:            
            from course_content_parser import CourseContentParser
            with open("inputs/" + ChatbotFront.course_file_path, "r", encoding="utf-8") as read_json_file:
                json_data = json.load(read_json_file)
                course_content = CourseContentParser.parse_course_content(json_data)
                if save_parsed_course:
                    serialized_data = course_content.to_dict()
                    with open('outputs/analysed_' + ChatbotFront.course_file_path, 'w') as write_analysed_file:
                        json.dump(serialized_data, write_analysed_file, indent=4)

        return course_content
