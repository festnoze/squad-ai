import time
from typing import Generator
import streamlit as st
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.llm_helper import Llm
from common_tools.models.conversation import Conversation
from common_tools.rag.rag_inference_pipeline.end_pipeline_exception import EndPipelineException

# internal import
from available_service import AvailableService
from scrape_service import ScrapeService

class ChatbotFront:
    def main():
        AvailableService.init()
        st.set_page_config(
            page_title= "Chatbot site public Studi.com",
            page_icon= "🔎",
            layout= "centered",
            initial_sidebar_state= "collapsed" #"expanded" #
        )

        custom_css = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .st-emotion-cache-1eo1tir {
                padding-top: 1rem !important;
                padding-bottom: 1rem !important;
            }
            .stSidebar {
                width: 360px !important;
            }
            </style>
            """
        st.markdown(custom_css, unsafe_allow_html=True)
        
        with st.sidebar:
            st.button('Utilisez le chatbot pour Rechercher  ➺', disabled=True)
            st.button('🧽 Effacer la conversation du chatbot', on_click=ChatbotFront.clear_conversation)
            st.divider()
            st.subheader('🚀 Autres actions :')
            st.button('📊 Récupérer données Drupal par json-api', on_click=ChatbotFront.get_drupal_data)
            st.button('📚 Scraping des pages web des formations', on_click=ChatbotFront.scrape_website_pages)
            st.button('📦 Construction de la base vectorielle', on_click=ChatbotFront.build_vectorstore)
            st.divider()
            st.button('✨ Générer RAGAS Ground Truth dataset', on_click=ChatbotFront.generate_ground_truth)
            #ChatbotFront.folder_path = st.text_input('Dossier à traiter', value=ChatbotFront.folder_path)#, disabled=True)

        st.title('💬 Chatbot Studi.com')
        # st.markdown('<h4 style='text-align: right;'><strong>🛰️ trouvez votre future formation</strong></h4>', unsafe_allow_html=True)
        st.caption(" Interroger notre base de connaissance sur : les métiers, nos formations, les financements, l'alternance, ...")
                
        if 'messages' not in st.session_state:
            st.session_state['messages'] = []
            st.session_state.messages.append({'role': 'assistant', 'content': ChatbotFront._start_caption()})
        if 'conversation' not in st.session_state:
            st.session_state['conversation'] = Conversation()
            st.session_state.conversation.add_new_message('assistant', ChatbotFront._start_caption())

        for msg in st.session_state.messages:
            st.chat_message(msg['role']).write(msg['content'])

        custom_css = """
            <style>
            .stSpinner {
                margin-left: 20px;
            }
            </style>
        """
        st.markdown(custom_css, unsafe_allow_html=True)
        if user_query := st.chat_input(placeholder= 'Ecrivez votre question ici ...'):
            user_query = txt.remove_markdown(user_query)
            st.session_state.messages.append({'role': 'user', 'content': user_query})
            st.session_state.conversation.add_new_message('user', user_query)
            st.chat_message('user').write_stream(ChatbotFront._write_stream(user_query))

            # # Without response streaming
            # with st.spinner('Recherche de réponses en cours ...'):
            #     conversation_history = Conversation([{ 'role': msg['role'], 'content': msg['content'] } for msg in st.session_state.messages])
            #     rag_answer = AvailableService.rag_query_full_pipeline_no_streaming_no_async(conversation_history, use_dynamic_pipeline=True)
            # rag_answer = txt.remove_markdown(rag_answer)
            # st.session_state.messages.append({'role': 'assistant', 'content': rag_answer})
            # with st.chat_message('assistant'):
            #     st.write(rag_answer)    

            # With response streaming
            all_chunks_output = []
            with st.chat_message('assistant'):
                with st.spinner('Je réfléchis à votre question ...'):
                    try:
                        analysed_query, retrieved_chunks = AvailableService.rag_query_retrieval_but_augmented_generation(st.session_state.conversation)             
                        pipeline_succeeded = True
                    except EndPipelineException as ex:                        
                        pipeline_succeeded = False
                        pipeline_ends_reason = ex.name
                        pipeline_ended_response = ex.message

                if pipeline_succeeded:
                    st.write_stream(AvailableService.rag_query_augmented_generation_streaming(analysed_query, retrieved_chunks[0], True, all_chunks_output))
                    full_response = ''.join(all_chunks_output)
                else:
                    st.write_stream(ChatbotFront._write_stream(pipeline_ended_response))
                    full_response = pipeline_ended_response

                st.session_state.conversation.add_new_message('assistant', full_response)
                st.session_state.messages.append({'role': 'assistant', 'content': full_response})

                # Ask for rating in case of conversation's ending
                if not pipeline_succeeded and  pipeline_ends_reason == '_fin_echange_':
                    feedback_value = st.feedback('stars', on_change=ChatbotFront._handle_feedback_change)
                    st.session_state['feedback_value'] = feedback_value

                # Replace RAG response by a generated summary used in streamlit cached conversation
                st.session_state.conversation.last_message.content = AvailableService.get_summarized_answer(st.session_state.conversation.last_message.content)

    def clear_conversation():
        st.session_state.messages = []
        st.session_state.messages.append({'role': 'assistant', 'content': ChatbotFront._start_caption()})

    def get_drupal_data():
        prompt = f'Récupération des données Drupal par json-api'
        with st.spinner('En cours ... ' + prompt):
            AvailableService.retrieve_all_data()
            st.session_state.messages.append({'role': 'assistant', 'content': txt.remove_markdown("Terminé avec succès : " + prompt)})

    def scrape_website_pages():
        prompt = f'Scraping des pages web des formations'
        with st.spinner('En cours ... ' + prompt):
            scraper = ScrapeService()
            scraper.scrape_all_trainings()            
            st.session_state.messages.append({'role': 'assistant', 'content': txt.remove_markdown("Terminé avec succès : " + prompt)})

    def build_vectorstore():        
        prompt = f'Construction de la base de données vectorielle'
        with st.spinner('En cours ... ' + prompt):
            AvailableService.create_vector_db_from_generated_embeded_documents(AvailableService.out_dir)
            st.session_state.messages.append({'role': 'assistant', 'content': txt.remove_markdown("Terminé avec succès : " + prompt)})
        
    def generate_ground_truth():
        prompt = f'Génération du dataset RAGAS Ground Truth'
        with st.spinner('En cours ... ' + prompt):
            AvailableService.generate_ground_truth()
            st.session_state.messages.append({'role': 'assistant', 'content': txt.remove_markdown("Terminé avec succès : " + prompt)})

    def _start_caption():
        return "Bonjour, je suis Studia, votre agent virtuel. Comment puis-je vous aider ?"
        
    def _handle_feedback_change():
        feedback_value = st.session_state.get('feedback_value')
        #st.session_state.chat_history.append(f"Feedback received: {feedback_value}")
        st.write(f"Feedback recorded as: {feedback_value}")

    def _write_stream(text: str, interval_btw_words:float = 0.02) -> Generator[str, None, None]:
        words = text.split(" ")
        for word in words:
            yield word + " "
            time.sleep(interval_btw_words)

if __name__ == "__main__":
    ChatbotFront.main() # startup with launching the chatbot