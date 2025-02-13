import os
import sys
import time
from dotenv import load_dotenv
from typing import Generator
import streamlit as st
import streamlit.components.v1 as components
from client_models.user_query_asking_request_model import UserQueryAskingRequestModel
from client_models.user_request_model import UserRequestModel
from common_tools.helpers.txt_helper import txt
from common_tools.models.conversation import Conversation
from common_tools.models.user import User
from common_tools.rag.rag_inference_pipeline.end_pipeline_exception import EndPipelineException
from chatbot_api_client import ChatbotApiClient

class ChatbotFront:
    def run():
        st.set_page_config(
            page_title= "Chatbot site public Studi.com",
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
            st.button("🚀 Chatbot du site public Studi.com à droite ➺", disabled=True)
            st.button('🧽 Effacer la conversation du chatbot', on_click=ChatbotFront.start_new_conversation)
            st.divider()

            st.subheader("💫 Paramétrage du pipeline d'ingestion")
            st.button("🔄 Re-démarrage de l'API RAG",               on_click=lambda: st.session_state.api_client.re_init_api())
            st.button("🧪 Tester tous les modèles d'inférence",   on_click=lambda: ChatbotFront.test_all_inference_models())
            st.button('📥 Récupérer données Drupal par json-api',   on_click=lambda: st.session_state.api_client.retrieve_all_data())
            st.button('🌐 Scraping des pages web des formations',   on_click=lambda: st.session_state.api_client.scrape_website_pages())
            st.button('🗂️ Construction de la base vectorielle',     on_click=lambda: st.session_state.api_client.build_vectorstore())
            st.button('🗃️ Construction base vectorielle synthétique + questions', on_click=lambda: st.session_state.api_client.build_summary_vectorstore())
            st.divider()
            
            st.subheader("💫 Evaluation du pipeline d'inference")
            st.button('✨ Générer RAGAS Ground Truth dataset',      on_click=lambda: st.session_state.api_client.generate_ground_truth())

        for msg in st.session_state.messages:
            st.chat_message(msg['role']).write(msg['content'])
        
        if user_query := st.chat_input(placeholder= 'Ecrivez votre question ici ...'):
            if not user_query.strip(): user_query = 'quels bts en rh ?'
            st.chat_message('user').write_stream(ChatbotFront._write_text_as_stream(user_query))
            st.session_state.messages.append({'role': 'user', 'content': user_query})
            st.session_state.conversation.add_new_message('user', user_query)

            with st.chat_message('assistant'):
                start = time.time()
                with st.spinner('Je réfléchis à votre question ...'):
                    request_model = UserQueryAskingRequestModel(conversation_id=st.session_state.conv_id, user_query_content=user_query)
                    streaming_response = st.session_state.api_client.rag_query_stream(request_model)
                    st.write_stream(streaming_response)
                    full_response = streaming_response
                    
                st.session_state.conversation.add_new_message('assistant', full_response)
                st.session_state.messages.append({'role': 'assistant', 'content': full_response})

                elapsed_time = time.time() - start
                txt.print(f"RAG full pipeline duration {txt.get_elapsed_str(elapsed_time)}")

    def start_new_conversation(): 
        st.session_state.messages = []        
        st.session_state.conversation = Conversation(st.session_state.user)
        st.session_state.conversation.add_new_message('assistant', ChatbotFront._start_caption())
        st.session_state.messages.append({
                            'role': st.session_state.conversation.last_message.role, 
                            'content': st.session_state.conversation.last_message.content})
        # Inform the API
        st.session_state.user_id = st.session_state.api_client.create_or_update_user(UserRequestModel(user_id=None, user_name=st.session_state.user.name))
        st.session_state.conv_id = st.session_state.api_client.create_new_conversation(st.session_state.user_id)

    def init_session():
        if 'messages' not in st.session_state:            
            st.session_state.user = User("fake user")
            st.session_state['messages'] = []
            st.session_state['conversation'] = Conversation(st.session_state.user)
            st.session_state['conv_id'] = None
            load_dotenv()
            st.session_state.api_host_uri =  os.getenv("API_HOST_URI")
            st.session_state.api_client = ChatbotApiClient(st.session_state.api_host_uri)
            ChatbotFront.start_new_conversation()

    def test_all_inference_models():
        tests_results = st.session_state.api_client.test_all_inference_models()
        result_msg = "Tous les modèles d'inférence configurés ont été testés avec les résultats suivants: \n\n"
        for result in tests_results['models_tests_results']:
            result_msg += f"- {result}\n"            
        st.write(result_msg)

    @staticmethod
    def _start_caption():
        return "Bonjour, je suis votre agent virtuel, StudIA. Comment puis-je vous aider ?"

    @staticmethod  
    def _handle_feedback_change():
        feedback_value = st.session_state.get('feedback_value', 5)
        feedback_msg = f"Merci pour votre retour. Nous avons bien enregistré votre note. A bientôt sur le chatbot Studi.com."
        st.session_state.messages[-1]['content'] = feedback_msg
        st.write(feedback_msg)

    @staticmethod
    def _write_text_as_stream(text: str, interval_btw_words:float = 0.02) -> Generator[str, None, None]:
        words = text.split(" ")
        for word in words:
            yield word + " "
            time.sleep(interval_btw_words)
