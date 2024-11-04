import streamlit as st
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.llm_helper import Llm
from common_tools.models.conversation import Conversation

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
            all_chunks_output = []
            with st.chat_message('assistant'):
                with st.spinner('Je réfléchis à votre question ...'):
                    analysed_query, retrieved_chunks = AvailableService.rag_query_retrieval_but_augmented_generation(st.session_state.conversation)
                st.write_stream(AvailableService.rag_query_augmented_generation_async(analysed_query, retrieved_chunks[0], True, all_chunks_output))
                full_response = ''.join(all_chunks_output)
                st.session_state.conversation.add_new_message('assistant', full_response)
                st.session_state.messages.append({'role': 'assistant', 'content': full_response})
        
                # Replace AI response by its summary in streamlit cached conversation
                st.session_state.conversation.last_message.content = AvailableService.summarize(st.session_state.conversation.last_message.content)
                b=3


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

if __name__ == "__main__":
    ChatbotFront.main() # startup with launching the chatbot