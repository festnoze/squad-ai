"""SkillForge Frontend - Streamlit Chatbot Application.

Based on OpaleCoursesWebscraper chatbot.py structure.
"""

import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any, Callable

import streamlit as st

from src.api.skillforge_client import SkillForgeClient, build_course_context
from src.config import Config
from src.models.course_content import CourseContent
from src.models.ressource_object import RessourceObject
from src.utils.course_loader import CourseLoader


class ChatbotFront:
    """Main chatbot frontend class managing UI and interactions."""

    # Class variables for state management
    api_client: SkillForgeClient | None = None
    loaded_course_content: CourseContent | None = None
    selected_course_name: str = ""
    previous_selected_course: str = ""
    selected_matiere = None
    selected_module = None
    selected_theme = None
    selected_ressource_object: RessourceObject | None = None
    current_thread_id: str | None = None
    start_caption = "Bonjour, je suis SkillForge, votre assistant d'apprentissage IA. Comment puis-je vous aider ?"

    @staticmethod
    def run():
        """Main application entry point."""
        ChatbotFront.init_session()

        st.set_page_config(
            page_title="SkillForge - Assistant IA d'apprentissage",
            page_icon="🎓",
            layout="wide",
            initial_sidebar_state="expanded",
        )

        custom_css = """\
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}

            /* Force sidebar to be visible and properly sized */
            section[data-testid="stSidebar"] {
                min-width: 400px !important;
                max-width: 500px !important;
                width: 450px !important;
                display: block !important;
                visibility: visible !important;
                transform: translateX(0) !important;
            }

            section[data-testid="stSidebar"] > div {
                min-width: 400px !important;
                max-width: 500px !important;
                width: 450px !important;
                transform: translateX(0) !important;
            }

            /* Ensure sidebar is visible when expanded */
            section[data-testid="stSidebar"][aria-expanded="true"] {
                display: block !important;
                visibility: visible !important;
                transform: translateX(0) !important;
            }

            /* Override any Streamlit classes that hide the sidebar */
            .st-emotion-cache-1k02nrb {
                transform: translateX(0) !important;
            }

            .st-emotion-cache-1eo1tir {
                padding-top: 1rem !important;
                padding-bottom: 1rem !important;
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

        # Display API initialization error if any
        if "api_init_error" in st.session_state:
            st.error(f"⚠️ Erreur d'initialisation de l'API client : {st.session_state['api_init_error']}")
            st.info("Veuillez configurer SKILLFORGE_JWT_TOKEN dans le fichier .env")

        # Check API connection status
        ChatbotFront.display_api_status()

        # Sidebar
        with st.sidebar:
            st.button("🧽 Effacer la conversation", on_click=ChatbotFront.start_new_conversation)

            st.divider()
            st.subheader("📚 Navigation du cours :")

            with st.expander("📖 Sélection du cours", expanded=True):
                ChatbotFront.render_course_navigation()

        # Main window
        # Web browser for resource display
        selected_resource_url = ChatbotFront.get_current_resource_url()
        if selected_resource_url:
            st.components.v1.iframe(selected_resource_url, height=600, scrolling=True)
        else:
            st.info("👈 Sélectionnez une ressource depuis le menu latéral pour la visualiser ici.")

        # Chatbot window
        for msg in st.session_state.messages:
            st.chat_message(msg["role"]).write(msg["content"])

        if user_query := st.chat_input(placeholder="Écrivez votre question ici ..."):
            if not user_query.strip():
                return

            st.chat_message("user").write(user_query)
            st.session_state.messages.append({"role": "user", "content": user_query})

            with st.chat_message("assistant"), st.spinner("Je réfléchis à votre question ..."):
                all_chunks_output = []
                streaming_response = ChatbotFront.answer_query_streaming(user_query, all_chunks_output)
                st.write_stream(streaming_response)
                full_response = "".join(all_chunks_output)
            # st.session_state.conversation.add_new_message('assistant', full_response)
            st.session_state.messages.append({"role": "assistant", "content": full_response})

    @staticmethod
    def render_course_navigation():
        """Render the course navigation UI."""
        # Load available courses
        available_courses = CourseLoader.load_available_courses()

        if not available_courses:
            st.warning("Aucun cours trouvé dans le dossier outputs/")
            st.info("Veuillez ajouter des fichiers JSON de cours dans le dossier outputs/ (format: *.json)")
            return

        # Course selection
        selected_course = st.selectbox("Sélection du cours", options=available_courses, index=0)

        # Load course if selection changed
        if selected_course != ChatbotFront.previous_selected_course:
            ChatbotFront.load_course(selected_course)
            ChatbotFront.previous_selected_course = selected_course

        if not ChatbotFront.loaded_course_content:
            return

        course = ChatbotFront.loaded_course_content

        # Matiere selection
        matieres = course.matieres
        if matieres:
            matiere_options = {f"{m.name} ({m.code})": m for m in matieres}
            selected_matiere_key = st.selectbox("📚 Matière", options=list(matiere_options.keys()), index=0)
            ChatbotFront.selected_matiere = matiere_options[selected_matiere_key]

            # Module selection
            modules = ChatbotFront.selected_matiere.modules if ChatbotFront.selected_matiere else []
            if modules:
                module_options = {f"{m.name} ({m.code})": m for m in modules}
                selected_module_key = st.selectbox("📂 Module", options=list(module_options.keys()), index=0)
                ChatbotFront.selected_module = module_options[selected_module_key]

                # Theme selection
                themes = ChatbotFront.selected_module.themes if ChatbotFront.selected_module else []
                if themes:
                    theme_options = {f"{t.name} ({t.code})": t for t in themes}
                    selected_theme_key = st.selectbox("📑 Thème", options=list(theme_options.keys()), index=0)
                    ChatbotFront.selected_theme = theme_options[selected_theme_key]

                    # Resource object selection
                    ressources = ChatbotFront.selected_theme.ressources if ChatbotFront.selected_theme else []
                    all_ressource_objects = []
                    for ressource in ressources:
                        all_ressource_objects.extend(ressource.ressource_objects)

                    if all_ressource_objects:
                        ro_options = {f"{ro.name} [{ro.type}]": ro for ro in all_ressource_objects}
                        selected_ro_key = st.selectbox("📄 Ressource", options=list(ro_options.keys()), index=0)
                        new_ro = ro_options[selected_ro_key]

                        # Reset thread if resource changed
                        if (
                            not ChatbotFront.selected_ressource_object
                            or new_ro.id != ChatbotFront.selected_ressource_object.id
                        ):
                            ChatbotFront.selected_ressource_object = new_ro
                            ChatbotFront.current_thread_id = None
                            st.success("✅ Ressource chargée ! Vous pouvez maintenant poser vos questions.")

    @staticmethod
    def start_new_conversation():
        """Clear conversation history and start fresh."""
        st.session_state.messages = []
        st.session_state.messages.append({"role": "assistant", "content": ChatbotFront.start_caption})
        ChatbotFront.current_thread_id = None

    @staticmethod
    def init_session():
        """Initialize Streamlit session state."""
        if "messages" not in st.session_state:
            st.session_state["messages"] = []
            st.session_state.messages.append({"role": "assistant", "content": ChatbotFront.start_caption})

        # Initialize API connection status
        if "api_connection_checked" not in st.session_state:
            st.session_state["api_connection_checked"] = False
            st.session_state["api_connection_status"] = None
            st.session_state["api_connection_message"] = ""

        # Initialize API client
        if not ChatbotFront.api_client:
            try:
                ChatbotFront.api_client = SkillForgeClient()
            except ValueError as e:
                # Don't stop - allow UI to render with error message
                st.session_state["api_init_error"] = str(e)
                ChatbotFront.api_client = None

        # Check API connection on first run (only if client initialized)
        if not st.session_state.api_connection_checked and ChatbotFront.api_client:
            ChatbotFront.check_api_connection()

    @staticmethod
    def load_course(course_name: str):
        """Load course content from JSON file."""
        try:
            ChatbotFront.loaded_course_content = CourseLoader.load_course_structure(course_name)
            ChatbotFront.selected_course_name = course_name
            # Reset navigation
            ChatbotFront.selected_matiere = None
            ChatbotFront.selected_module = None
            ChatbotFront.selected_theme = None
            ChatbotFront.selected_ressource_object = None
            ChatbotFront.current_thread_id = None
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"Cours '{course_name}' chargé avec succès.",
            })
        except Exception as e:
            st.error(f"Erreur lors du chargement du cours : {e}")
            ChatbotFront.loaded_course_content = None

    @staticmethod
    def get_current_resource_url() -> str:
        """Get URL of currently selected resource."""
        if ChatbotFront.selected_ressource_object:
            return ChatbotFront.selected_ressource_object.url
        return ""

    @staticmethod
    def answer_query_streaming(user_query: str, all_chunks_output: list[str]) -> Generator[str, None, None]:
        """Answer user query with streaming response from API.

        Returns a sync generator that wraps the async streaming response.
        This generator is compatible with st.write_stream().
        """
        if not ChatbotFront.selected_ressource_object:
            error_msg = "Veuillez d'abord sélectionner une ressource (menu latéral)."
            st.error(error_msg)
            yield error_msg
            return

        try:
            # Get or create thread
            if not ChatbotFront.current_thread_id:
                course_context = ChatbotFront.build_current_course_context()
                threads_ids = asyncio.run(ChatbotFront.api_client.aget_user_all_threads_ids_or_create(course_context))
                ChatbotFront.current_thread_id = threads_ids[0]

            # Build course context for the query
            course_context = ChatbotFront.build_current_course_context()

            # Wrap the async streaming method to sync generator
            sync_generator = ChatbotFront.async_generator_wrapper_to_sync(
                ChatbotFront.api_client.asend_query_streaming,
                ChatbotFront.current_thread_id,
                user_query,
                course_context,
            )

            # Yield chunks from the sync generator
            for chunk in sync_generator:
                all_chunks_output.append(chunk)
                yield chunk

        except Exception as e:
            error_msg = f"Erreur lors de la génération de la réponse : {e}"
            st.error(error_msg)
            yield error_msg

    @staticmethod
    def build_current_course_context() -> dict:
        """Build course context dict from current selection."""
        ro = ChatbotFront.selected_ressource_object
        theme = ChatbotFront.selected_theme
        module = ChatbotFront.selected_module
        matiere = ChatbotFront.selected_matiere
        course = ChatbotFront.loaded_course_content
        ressource_type = ro.type if ro else None
        # Set 'Opale' type to 'interactive'
        if ressource_type == "opale":
            ressource_type = "interactive"

        return build_course_context(
            ressource_id=str(ro.id) if ro else None,
            ressource_type=ressource_type,
            ressource_code=None,
            ressource_title=ro.name if ro else None,
            ressource_url=ro.url if ro else None,
            theme_id=str(theme.id) if theme else None,
            module_id=str(module.id) if module else None,
            matiere_id=str(matiere.id) if matiere else None,
            parcour_id=str(course.parcours_id) if course else None,
            parcours_name=course.name if course else None,
        )

    @staticmethod
    def check_api_connection():
        """Check API connection and store result in session state."""
        try:
            success, message = asyncio.run(ChatbotFront.api_client.aping())
            st.session_state.api_connection_status = success
            st.session_state.api_connection_message = message
            st.session_state.api_connection_checked = True
        except Exception as e:
            st.session_state.api_connection_status = False
            st.session_state.api_connection_message = f"Erreur lors de la vérification : {e}"
            st.session_state.api_connection_checked = True

    @staticmethod
    def display_api_status():
        """Display API connection status banner."""
        if not st.session_state.api_connection_checked:
            return

        if st.session_state.api_connection_status:
            # Success - show small success message
            st.success(f"✅ {st.session_state.api_connection_message} at: '{Config.SKILLFORGE_API_URL}'")
        else:
            # Error - show prominent error message
            st.error(f"❌ Erreur de connexion API : {st.session_state.api_connection_message}")
            st.warning(
                f"⚠️ Impossible de se connecter à l'API SkillForge à l'adresse : {Config.SKILLFORGE_API_URL}\n\n"
                "Veuillez vérifier que :\n"
                "- L'API backend est démarrée\n"
                "- L'URL dans le fichier .env est correcte\n"
                "- Le token JWT est valide"
            )

            # Add a retry button
            if st.button("🔄 Réessayer la connexion"):
                st.session_state.api_connection_checked = False
                st.rerun()

    # Copied from common_tools
    @staticmethod
    def async_generator_wrapper_to_sync(
        function_to_call: Callable[..., AsyncGenerator], *args: Any, **kwargs: Any
    ) -> Generator:
        """
        Convert an asynchronous generator function to a synchronous generator.
        Use asyncio.Queue to bridge async results to the sync context.
        """

        async def put_results_in_queue(loop: asyncio.AbstractEventLoop):
            # Collect the results from the async generator and put them in the queue
            try:
                async for chunk in function_to_call(*args, **kwargs):
                    await queue.put(chunk)
                await queue.put(None)  # Indicate the end of the stream
            except Exception as e:
                await queue.put(e)  # Pass exceptions to the sync consumer

        def _raise_runtime_error():
            raise RuntimeError

        # Create an event loop or use the existing one
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                _raise_runtime_error()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Create a queue to stream results from the async context to the sync context
        queue = asyncio.Queue()

        # Run the async producer in the same loop - store reference to prevent garbage collection
        _ = loop.create_task(put_results_in_queue(loop))  # noqa: RUF006
        # Consume results from the queue synchronously
        while True:
            item = loop.run_until_complete(queue.get())
            if item is None:  # End of the stream
                break
            if isinstance(item, Exception):  # Handle exceptions
                raise item
            yield item
