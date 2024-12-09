# Modified streamlit code using ChatbotApiClient

import os
import sys
import time
from typing import Generator
from dotenv import load_dotenv
import streamlit as st
import streamlit.components.v1 as components
from common_tools.helpers.txt_helper import txt
from common_tools.models.conversation import Conversation
from common_tools.rag.rag_inference_pipeline.end_pipeline_exception import EndPipelineException
from chatbot_api_client import ChatbotApiClient

class ChatbotFront:
    def main():
        load_dotenv()
        api_host_uri =  os.getenv("API_HOST_URI")
        api_client = ChatbotApiClient(api_host_uri)

        st.set_page_config(
            page_title= "Chatbot site public Studi.com",
            page_icon= "🔎",
            layout= "centered",
            initial_sidebar_state= "collapsed"
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
                width: 365px !important;
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
            st.button('Utilisez le chatbot pour Rechercher  ➺', disabled=True)
            st.button('🧽 Effacer la conversation du chatbot', on_click=ChatbotFront.clear_conversation)
            st.divider()
            st.subheader('🚀 Autres actions :')
            st.button('📊 Récupérer données Drupal par json-api', on_click=lambda: api_client.retrieve_all_data())
            st.button('📚 Scraping des pages web des formations', on_click=lambda: api_client.scrape_website_pages())
            st.button('📦 Construction de la base vectorielle', on_click=lambda: api_client.build_vectorstore())
            st.button('📦 Construction de la base résumée', on_click=lambda: api_client.build_summary_vectorstore())
            st.divider()
            st.button('✨ Générer RAGAS Ground Truth dataset', on_click=lambda: api_client.generate_ground_truth())

        if 'messages' not in st.session_state:
            st.session_state['messages'] = []
            st.session_state.messages.append({'role': 'assistant', 'content': ChatbotFront._start_caption()})
        if 'conversation' not in st.session_state:
            st.session_state['conversation'] = Conversation()
            st.session_state.conversation.add_new_message('assistant', ChatbotFront._start_caption())

        for msg in st.session_state.messages:
            st.chat_message(msg['role']).write(msg['content'])
        
        if user_query := st.chat_input(placeholder= 'Ecrivez votre question ici ...'):
            if not user_query.strip():
                user_query = 'quels bts en rh ?'
            st.chat_message('user').write_stream(ChatbotFront._write_stream(user_query))
            st.session_state.messages.append({'role': 'user', 'content': user_query})
            st.session_state.conversation.add_new_message('user', user_query)

            with st.chat_message('assistant'):
                start = time.time()
                with st.spinner('Je réfléchis à votre question ...'):
                    conv_id = api_client.create_new_conversation('streamlit')
                    resp = api_client.rag_query_stream(conv_id, user_query)
                    st.write_stream(ChatbotFront._write_stream(resp))
                    full_response = resp

                st.session_state.conversation.add_new_message('assistant', full_response)
                st.session_state.messages.append({'role': 'assistant', 'content': full_response})

                elapsed_time = time.time() - start
                txt.print(f"RAG full pipeline duration {txt.get_elapsed_str(elapsed_time)}")

    @staticmethod
    def clear_conversation():
        st.session_state.messages = []
        st.session_state.conversation = Conversation()
        st.session_state.messages.append({'role': 'assistant', 'content': ChatbotFront._start_caption()})
        st.session_state.conversation.add_new_message('assistant', ChatbotFront._start_caption())

    @staticmethod
    def _start_caption():
        return "Bonjour, je suis Studia, votre agent virtuel. Comment puis-je vous aider ?"

    @staticmethod  
    def _handle_feedback_change():
        feedback_value = st.session_state.get('feedback_value', 5)
        feedback_msg = f"Merci pour votre retour. Nous avons bien enregistré votre note. A bientôt sur le chatbot Studi.com."
        st.session_state.messages[-1]['content'] = feedback_msg
        st.write(feedback_msg)

    @staticmethod
    def _write_stream(text: str, interval_btw_words:float = 0.02) -> Generator[str, None, None]:
        words = text.split(" ")
        for word in words:
            yield word + " "
            time.sleep(interval_btw_words)
