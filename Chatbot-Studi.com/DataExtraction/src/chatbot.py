import streamlit as st
from common_tools.helpers.txt_helper import txt
from common_tools.models.conversation import Conversation

# internal import
from available_service import AvailableService

class ChatbotFront:
    def main():
        AvailableService.init()

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
            st.button("✨ Générer RAGAS Ground Truth", on_click=ChatbotFront.generate_ground_truth)
            # st.button("📊 Analyser structures des fichiers C#", on_click=ChatbotFront.analyse_files_code_structures)
            # st.button("📦 Ajouter fichiers analysés à la base", on_click= ChatbotFront.vectorize_summaries)
            # st.button("📚 Créer documentation du code C#", on_click= ChatbotFront.generate_documentations, disabled=True)
            #ChatbotFront.folder_path = st.text_input("Dossier à traiter", value=ChatbotFront.folder_path)#, disabled=True)

        st.title("💬 Chatbot Studi.com")
        # st.markdown("<h4 style='text-align: right;'><strong>🛰️ trouvez votre future formation</strong></h4>", unsafe_allow_html=True)
        st.caption(" Interroger notre base de connaissance sur : les métiers, nos formations, les financements, l'alternance, ...")
                
        if "messages" not in st.session_state:
            st.session_state["messages"] = []

        if not any(st.session_state.messages):
            st.session_state.messages.append({"role": "assistant", "content": ChatbotFront.start_caption()})

        for msg in st.session_state.messages:
            st.chat_message(msg["role"]).write(msg["content"])
                    
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

            # with st.spinner("Recherche de réponses en cours ..."):
            #     #rag_answer = AvailableService.rag_query(prompt)
            #     conversation_history = Conversation([{ 'role': msg['role'], 'content': msg['content'] } for msg in st.session_state.messages])
            #     rag_answer = AvailableService.rag_query_with_history(conversation_history)

            # rag_answer = txt.remove_markdown(rag_answer)
            # st.session_state.messages.append({"role": "assistant", "content": rag_answer})
            # st.chat_message("assistant").write(rag_answer)    
            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                full_response = ""

                # Simulate stream of response
                for chunk in AvailableService.rag_query_with_history_async(prompt):
                    full_response += chunk
                    message_placeholder.markdown(full_response + "▌")

                message_placeholder.markdown(full_response)  # Remove cursor when done

                # Append assistant response
                st.session_state["messages"].append({"role": "assistant", "content": full_response})    

    def clear_conversation():
        st.session_state.messages = []
        st.session_state.messages.append({"role": "assistant", "content": ChatbotFront.start_caption()})

    def generate_ground_truth():
        prompt = f"Génération du dataset RAGAS Ground Truth"
        with st.spinner("En cours ... " + prompt):
            AvailableService.generate_ground_truth()
        st.session_state.messages.append({"role": "assistant", "content": txt.remove_markdown("Terminé avec succès : " + prompt)})

    def start_caption():
        return "Bonjour, je suis Studia, votre agent virtuel. Comment puis-je vous aider ?"

if __name__ == "__main__":
    ChatbotFront.main()