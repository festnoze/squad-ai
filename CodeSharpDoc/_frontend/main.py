# import streamlit as st

# def main():
#     st.title("Assistant de Projet C#")

#     # Initialisation de st.session_state.messages
#     if "messages" not in st.session_state:
#         st.session_state.messages = []
#         st.session_state.messages.append({"role": "assistant", "content": """
# 1. Générer et remplacer les résumés pour tous les fichiers C# du projet
# 2. Analyser les structures de code et les résumés et sauvegarder en fichiers JSON
# 3. Construire une nouvelle base de données vectorielle à partir des fichiers JSON de structures analysées
# 4. Interroger le service RAG sur la base de données vectorielle
# 5. Aide : Afficher ce menu à nouveau
# 6. Quitter
#         """})

#     # Affichage des messages
#     for message in st.session_state.messages:
#         with st.chat_message(message["role"]):
#             st.markdown(message["content"])

#     if prompt := st.chat_input("Entrez votre choix ou posez une question"):
#         st.session_state.messages.append({"role": "user", "content": prompt})
#         with st.chat_message("user"):
#             st.markdown(prompt)

#         # Logique pour traiter les entrées de l'utilisateur
#         response = handle_user_input(prompt)
        
#         st.session_state.messages.append({"role": "assistant", "content": response})
#         with st.chat_message("assistant"):
#             st.markdown(response)

# def handle_user_input(prompt):
#     if prompt == "1":
#         return "Fonctionnalité 1 : Générer et remplacer les résumés pour tous les fichiers C# du projet."
#     elif prompt == "2":
#         return "Fonctionnalité 2 : Analyser les structures de code et les résumés et sauvegarder en fichiers JSON."
#     elif prompt == "3":
#         return "Fonctionnalité 3 : Construire une nouvelle base de données vectorielle à partir des fichiers JSON de structures analysées."
#     elif prompt == "4":
#         return "Fonctionnalité 4 : Interroger le service RAG sur la base de données vectorielle."
#     elif prompt == "5":
#         return """
# 1. Générer et remplacer les résumés pour tous les fichiers C# du projet
# 2. Analyser les structures de code et les résumés et sauvegarder en fichiers JSON
# 3. Construire une nouvelle base de données vectorielle à partir des fichiers JSON de structures analysées
# 4. Interroger le service RAG sur la base de données vectorielle
# 5. Aide : Afficher ce menu à nouveau
# 6. Quitter
#         """
#     elif prompt == "6":
#         return "Quitter : Merci d'avoir utilisé l'assistant de projet C#."
#     else:
#         return "Option non reconnue. Veuillez entrer un numéro valide."

# if __name__ == "__main__":
#     main()
from openai import OpenAI
import streamlit as st

with st.sidebar:
    openai_api_key = st.text_input("OpenAI API Key", key="chatbot_api_key", type="password")
    "[Get an OpenAI API key](https://platform.openai.com/account/api-keys)"
    "[View the source code](https://github.com/streamlit/llm-examples/blob/main/Chatbot.py)"
    "[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/streamlit/llm-examples?quickstart=1)"

st.title("💬 Chatbot")
st.caption("🚀 A Streamlit chatbot powered by OpenAI")
if "messages" not in st.session_state:
    st.session_state["messages"] = [{"role": "assistant", "content": "How can I help you?"}]

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

if prompt := st.chat_input():
    if not openai_api_key:
        st.info("Please add your OpenAI API key to continue.")
        st.stop()

    client = OpenAI(api_key=openai_api_key)
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)
    response = client.chat.completions.create(model="gpt-3.5-turbo", messages=st.session_state.messages)
    msg = response.choices[0].message.content
    st.session_state.messages.append({"role": "assistant", "content": msg})
    st.chat_message("assistant").write(msg)