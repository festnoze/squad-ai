import streamlit as st
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.llm_helper import Llm
from common_tools.models.conversation import Conversation

# internal import
from available_service import AvailableService
from drupal_data_retireval import DrupalDataRetireval
from scrape_service import ScrapeService

class ChatbotFront:
    def main():
        AvailableService.init()
        st.set_page_config(
            page_title= "Chatbot site public Studi.com",
            page_icon= "🔎",
            layout= "centered",
            initial_sidebar_state= "expanded" #"collapsed" #
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
            st.button('📦 Remplissage de la base vectorielle', on_click=ChatbotFront.build_vectorstore)
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
        if prompt := st.chat_input(placeholder= 'Ecrivez votre question ici ...'):
            prompt = txt.remove_markdown(prompt)
            st.session_state.messages.append({'role': 'user', 'content': prompt})
            st.session_state.conversation.add_new_message('user',prompt)
            st.chat_message('user').write(prompt)

            # # Without response streaming
            # with st.spinner('Recherche de réponses en cours ...'):
            #     conversation_history = Conversation([{ 'role': msg['role'], 'content': msg['content'] } for msg in st.session_state.messages])
            #     rag_answer = AvailableService.rag_query_with_history_wo_streaming(conversation_history)
            # rag_answer = txt.remove_markdown(rag_answer)
            # st.session_state.messages.append({'role': 'assistant', 'content': rag_answer})
            # st.chat_message('assistant').write(rag_answer)    

            # With response streaming
            with st.chat_message('assistant'):
                with st.spinner('Je réfléchis à votre question ...'):
                    all_chunks_output = []
                    st.write_stream(AvailableService.rag_query_with_history_streaming(st.session_state.conversation, all_chunks_output))
                    full_response = ''.join([chunk.decode('utf-8').replace(Llm.new_line_for_stream_over_http, '\n') for chunk in all_chunks_output])
                    st.session_state.conversation.add_new_message('assistant', full_response)
                    st.session_state.messages.append({'role': 'assistant', 'content': full_response})
            
            # Replace AI response by a summary
            st.session_state.conversation.last_message.content = AvailableService.summarize(st.session_state.conversation.last_message.content)
            a=0

    def clear_conversation():
        st.session_state.messages = []
        st.session_state.messages.append({'role': 'assistant', 'content': ChatbotFront._start_caption()})

    def get_drupal_data():
        drupal = DrupalDataRetireval(AvailableService.out_dir)
        drupal.retrieve_all_data()

    def build_vectorstore():
        AvailableService.create_vector_db_from_generated_embeded_documents(AvailableService.out_dir)
        
    def scrape_website_pages():
        scraper = ScrapeService()
        scraper.scrape_all_trainings()

    def generate_ground_truth():
        prompt = f'Génération du dataset RAGAS Ground Truth'
        with st.spinner('En cours ... ' + prompt):
            AvailableService.generate_ground_truth()
            st.session_state.messages.append({'role': 'assistant', 'content': txt.remove_markdown("Terminé avec succès : " + prompt)})

    def _start_caption():
        return "Bonjour, je suis Studia, votre agent virtuel. Comment puis-je vous aider ?"

if __name__ == "__main__":
    ChatbotFront.main()