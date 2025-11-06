"""SkillForge Frontend - Streamlit Chatbot Application.

Based on OpaleCoursesWebscraper chatbot.py structure.
"""

import asyncio
import base64
import os
from collections.abc import AsyncGenerator, Generator
from typing import Any, Callable

import httpx
import streamlit as st

from src.api_client.skillforge_api_client import SkillForgeAPIClient, build_course_context
from src.config import Config
from src.course_content_parser import CourseContentParser
from src.models.course_content import CourseContent
from src.models.ressource_object import RessourceObject
from src.utils.course_loader import CourseLoader


class ChatbotFront:
    """Main chatbot frontend class managing UI and interactions."""

    # Class variables for state management
    api_client: SkillForgeAPIClient | None = None
    selected_course: CourseContent | None = None
    selected_course_name: str = ""
    previous_selected_course: CourseContent | None = None
    selected_matiere = None
    selected_module = None
    selected_theme = None
    selected_ressource_object: RessourceObject | None = None
    current_thread_id: str | None = None
    thread_messages_to_be_reloaded: bool = False
    start_caption = "Bonjour, je suis SkillForge, votre assistant d'apprentissage IA. Comment puis-je vous aider ?"
    parcour_composition_file_path = ""
    output_folder = "outputs/"
    analysed_parcour_file_path = ""
    analysed_parcour_index = 0

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

        ChatbotFront.apply_custom_css()

        # Display API initialization error if any
        if "api_init_error" in st.session_state:
            st.error(f"⚠️ Erreur d'initialisation de l'API client : {st.session_state['api_init_error']}")
            st.info("Veuillez configurer SKILLFORGE_JWT_TOKEN dans le fichier .env")

        # Check API connection status
        ChatbotFront.display_api_status()

        # Handle scraping trigger (before sidebar to show progress in main area)
        if st.session_state.get("trigger_scraping", False):
            st.session_state["trigger_scraping"] = False  # Reset trigger
            course_name = st.session_state.get("scraping_course", "")
            if course_name:
                ChatbotFront.scrape_parcour_all_courses_opale(course_name)
                return  # Don't auto-rerun - let user see the results and manually continue

        # Sidebar
        with st.sidebar:
            st.subheader("🔍 Analyser Inscriptions utilisateur")
            with st.expander("💫 JSON réponse du endpoint '/parcours' LMS"):
                input_folder = "inputs/"
                input_json_files = ["-"] + [f for f in os.listdir(input_folder) if f.endswith(".json")]
                ChatbotFront.parcour_composition_index = 0

                if ChatbotFront.parcour_composition_file_path in input_json_files:
                    ChatbotFront.parcour_composition_index = input_json_files.index(
                        ChatbotFront.parcour_composition_file_path
                    )

                ChatbotFront.parcour_composition_file_path = st.selectbox(
                    "Fichier *.json des inscriptions aux parcours (depuis 'inputs')",
                    options=input_json_files,
                    index=ChatbotFront.parcour_composition_index,
                )
                st.button(
                    "🧪 Analyser la composition du parcours",
                    on_click=lambda: ChatbotFront.analyse_parcours_file_composition_click(),
                    use_container_width=True,
                )

            st.subheader("🧭 Navigation")

            with st.expander("🎓 Sélection du parcours", expanded=True):
                ChatbotFront.render_course_selection()
            with st.expander("📖 Sélection du cours", expanded=True):
                ChatbotFront.render_course_hierarchy_selection()
            st.divider()
            st.button(
                "🗑️  Effacer la conversation", on_click=ChatbotFront.start_new_conversation, use_container_width=True
            )

        # Main window
        # Web browser for resource display
        selected_resource_url = ChatbotFront.get_current_resource_url()
        if selected_resource_url:
            # Try to load content from web browser first
            if not ChatbotFront.load_url_content_in_web_browser(selected_resource_url):
                # If web loading fails, load from database
                ChatbotFront.load_content_from_database(selected_resource_url)
        else:
            st.info("👈 Sélectionnez une ressource depuis le menu latéral pour la visualiser ici.")

        # Chatbot window
        # Load thread messages if flag is set
        if ChatbotFront.thread_messages_to_be_reloaded:
            asyncio.run(ChatbotFront.aload_context_thread_messages())

        for msg in st.session_state.messages:
            st.chat_message(msg["role"]).write(msg["content"])

        if user_query := st.chat_input(placeholder="Posez votre question ici ..."):
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
    def render_course_selection():
        """Render the course selection UI."""
        # Load available courses
        CourseLoader.available_courses = CourseLoader.load_available_courses()

        if not any(CourseLoader.available_courses):
            st.warning("Aucun cours trouvé dans le dossier outputs/")
            st.info("Veuillez ajouter des fichiers JSON de cours dans le dossier outputs/ (format: *.json)")
            return

        # Course selection
        ChatbotFront.selected_course = st.selectbox(
            "Sélection du parcours", options=CourseLoader.available_courses, index=0
        )

        with st.expander("⚙️ Actions sur le parcours", expanded=False):
            ChatbotFront.render_course_actions()

    @staticmethod
    def render_course_actions():
        if st.button("💾 Persistance BDD de la hiérarchie parcours", use_container_width=True):
            ChatbotFront.save_course_hierarchy_to_db(ChatbotFront.selected_course)

        # Button to trigger scraping - use session state instead of on_click callback
        if st.button("🧲 Scraping Web de tous les cours du parcours", use_container_width=True):
            st.session_state["trigger_scraping"] = True
            st.session_state["scraping_course"] = ChatbotFront.selected_course

        # Load course if course selection has changed
        if ChatbotFront.selected_course != ChatbotFront.previous_selected_course:
            ChatbotFront.load_course(ChatbotFront.selected_course)
            ChatbotFront.previous_selected_course = ChatbotFront.selected_course

    @staticmethod
    def render_course_hierarchy_selection():
        """Render the course hierarchy selection UI."""
        # Skip hierarchy selection if no course is selected
        if not ChatbotFront.selected_course:
            return

        # Matiere selection
        matieres = ChatbotFront.selected_course.matieres
        if matieres:
            matiere_options = {m.name: m for m in matieres}
            selected_matiere_key = st.selectbox("📚 Matière", options=list(matiere_options.keys()), index=0)
            ChatbotFront.selected_matiere = matiere_options[selected_matiere_key]

            # Module selection
            modules = ChatbotFront.selected_matiere.modules if ChatbotFront.selected_matiere else []
            if modules:
                module_options = {m.name: m for m in modules}
                selected_module_key = st.selectbox("📂 Module", options=list(module_options.keys()), index=0)
                ChatbotFront.selected_module = module_options[selected_module_key]

                # Theme selection
                themes = ChatbotFront.selected_module.themes if ChatbotFront.selected_module else []
                if themes:
                    theme_options = {t.name: t for t in themes}
                    selected_theme_key = st.selectbox("📑 Thème", options=list(theme_options.keys()), index=0)
                    ChatbotFront.selected_theme = theme_options[selected_theme_key]

                    # Resource object selection
                    ressources = ChatbotFront.selected_theme.ressources if ChatbotFront.selected_theme else []
                    all_ressource_objects = []
                    for ressource in ressources:
                        all_ressource_objects.extend(ressource.ressource_objects)

                    if all_ressource_objects:
                        ro_options = {ro.name: ro for ro in all_ressource_objects}
                        selected_ro_key = st.selectbox("📄 Ressource", options=list(ro_options.keys()), index=0)
                        new_ro = ro_options[selected_ro_key]

                        # Mark messages to be reloaded if selected resource has changed
                        if (
                            not ChatbotFront.selected_ressource_object
                            or ChatbotFront.selected_ressource_object.id != new_ro.id
                        ):
                            ChatbotFront.selected_ressource_object = new_ro
                            ChatbotFront.thread_messages_to_be_reloaded = True

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
                ChatbotFront.api_client = SkillForgeAPIClient()
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
            ChatbotFront.selected_course = CourseLoader.load_course_structure(course_name)
            ChatbotFront.selected_course_name = course_name
            # Reset navigation
            ChatbotFront.selected_matiere = None
            ChatbotFront.selected_module = None
            ChatbotFront.selected_theme = None
            ChatbotFront.selected_ressource_object = None
            ChatbotFront.current_thread_id = None
            # st.session_state.messages.append({"role": "assistant", "content": f"Cours '{course_name}' chargé avec succès."})
        except Exception as e:
            st.error(f"Erreur lors du chargement du cours : {e}")
            ChatbotFront.selected_course = None

    @staticmethod
    def get_current_resource_url() -> str:
        """Get URL of currently selected resource."""
        if ChatbotFront.selected_ressource_object:
            return ChatbotFront.selected_ressource_object.url
        return ""

    @staticmethod
    def load_url_content_in_web_browser(resource_url: str) -> bool:
        """Try to load and display resource content from the web URL in iframe.

        Checks if the web URL is accessible and displays it in an iframe.
        Returns False if the web URL is not accessible or fails to load.

        Args:
            resource_url: URL of the resource to display

        Returns:
            True if web content was successfully loaded and displayed, False otherwise
        """
        try:
            # Quick check if URL is accessible (with timeout)
            is_accessible = asyncio.run(ChatbotFront._acheck_url_accessible(resource_url))
            if is_accessible:
                # Web URL is accessible, display in iframe
                st.components.v1.iframe(resource_url, height=600, scrolling=True)
                return True
        except Exception as e:
            st.error(f"❌ Erreur lors du chargement du contenu depuis le web: {e}")

        # Web URL is not accessible
        return False

    @staticmethod
    def load_content_from_database(resource_url: str) -> None:
        """Load and display HTML content from database as fallback.

        Retrieves HTML content from the database via API and displays it in an iframe
        using base64 encoding. Shows appropriate status messages and errors.

        Args:
            resource_url: URL of the resource to retrieve from database
        """
        try:
            st.info("🔄 Le contenu web n'est pas accessible. Chargement depuis la base de données...")

            # Get HTML content from database via API
            content_data = asyncio.run(ChatbotFront.api_client.aget_content_html_by_url(resource_url))

            if content_data and content_data.get("status") == "success":
                html_content = content_data.get("content_html", "")

                if html_content:
                    # Display HTML in an iframe using base64 encoding
                    html_b64 = base64.b64encode(html_content.encode("utf-8")).decode("utf-8")
                    iframe_src = f"data:text/html;base64,{html_b64}"

                    st.components.v1.iframe(iframe_src, height=600, scrolling=True)
                    st.success("✅ Contenu chargé depuis la base de données")
                else:
                    st.warning("⚠️ Contenu HTML vide dans la base de données")
            else:
                st.error(
                    f"❌ Impossible de charger le contenu depuis la base de données: {content_data.get('message', 'Erreur inconnue')}"
                )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                st.error("❌ Contenu non trouvé dans la base de données. Veuillez d'abord scraper ce contenu.")
            else:
                st.error(f"❌ Erreur lors du chargement depuis la base de données: {e}")
        except Exception as e:
            st.error(f"❌ Erreur inattendue lors du chargement du contenu: {e}")

    @staticmethod
    def analyse_parcours_file_composition_click() -> None:
        analysed_parcour_content_by_parcour_name = CourseContentParser.analyse_parcours_file_composition(
            ChatbotFront.parcour_composition_file_path
        )

        st.chat_message("assistant").write(
            f'Le contenu du parcours suivant à été analysé à partir du fichier de description: "{ChatbotFront.parcour_composition_file_path}"'
        )
        for parcour_name in analysed_parcour_content_by_parcour_name:
            st.chat_message("assistant").write(
                f'Le fichier analysé contenait le parcours : "{parcour_name}" dont la structure a été enregistré dans "outputs".'
            )
        st.chat_message("assistant").write(
            "Le nom du fichier analysé à été mis dans le champ de sélection de fichier analysé pour le scraping du contenu de tous les cours du parcours."
        )

        # Refresh the list of available courses
        CourseLoader.available_courses = CourseLoader.load_available_courses()

    @staticmethod
    async def _acheck_url_accessible(url: str, timeout: float = 3.0) -> bool:
        """Check if a URL is accessible.

        Args:
            url: URL to check
            timeout: Timeout in seconds

        Returns:
            True if URL is accessible (status code 200-399), False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.head(url, follow_redirects=True)
                return 200 <= response.status_code < 400
        except Exception:
            return False

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
            # Build course context for the query
            course_context = ChatbotFront.build_current_course_context()

            # Get or create thread
            if not ChatbotFront.current_thread_id:
                threads_ids = asyncio.run(ChatbotFront.api_client.aget_user_all_threads_ids_or_create(course_context))
                ChatbotFront.current_thread_id = threads_ids[0]

            # Wrap the async streaming method to sync generator
            sync_generator = ChatbotFront.async_generator_wrapper_to_sync(
                ChatbotFront.api_client.asend_query_streaming,
                ChatbotFront.current_thread_id,
                user_query,
                course_context,
                "",  # selected text
                all_chunks_output,
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
        course = ChatbotFront.selected_course
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
    async def aload_context_thread_messages():
        """Load thread messages for the current resource context.

        This method:
        1. Builds the course context from current selection
        2. Gets or creates thread IDs for the context
        3. Retrieves thread messages from the API
        4. Updates st.session_state.messages with the retrieved messages
        5. Resets the thread_messages_to_be_reloaded flag
        """
        import time

        try:
            start_time = time.time()
            with st.spinner("Chargement des messages existants pour le cours ..."):
                course_context = ChatbotFront.build_current_course_context()
                threads_ids = await ChatbotFront.api_client.aget_user_all_threads_ids_or_create(course_context)
                # get_thread_duration = time.time() - start_time
                # st.success(f"✅ Conversation chargée ({get_thread_duration:.2f}s).")
                ChatbotFront.current_thread_id = threads_ids[0]
                thread = await ChatbotFront.api_client.aget_thread_messages(ChatbotFront.current_thread_id)
                st.session_state.messages = thread["messages"]
            duration = time.time() - start_time
            st.success(f"✅ Conversation et messages chargés (en {duration:.2f}s).")
        except Exception as e:
            st.error(f"❌ Erreur lors du chargement des messages ou des conversations : {e}")
        finally:
            # Reset the flag
            ChatbotFront.thread_messages_to_be_reloaded = False

    @staticmethod
    def calculate_estimated_time_remaining(
        start_time: float, successful_count: int, total_resources: int, current_index: int
    ) -> str:
        """Calculate estimated remaining time based on average processing time.

        Args:
            start_time: Timestamp when scraping started (from time.time())
            successful_count: Number of successfully scraped resources
            total_resources: Total number of resources to process
            current_index: Current resource index being processed

        Returns:
            Formatted string with estimated remaining time (e.g., "⏱️ ~5.2 min restantes")
        """
        import time

        # Handle edge case: no successful scrapes yet
        if successful_count == 0:
            return "⏱️ -"

        # Handle edge case: all resources processed
        if current_index >= total_resources:
            return "⏱️ 0 sec restantes"

        # Calculate elapsed time
        elapsed_time = time.time() - start_time

        # Handle edge case: negative or zero elapsed time
        if elapsed_time <= 0:
            return "⏱️ -"

        # Calculate average time per successfully scraped resource
        avg_time_per_resource = elapsed_time / successful_count

        # Calculate remaining resources (total - current)
        remaining_resources = total_resources - current_index

        # Handle edge case: no remaining resources
        if remaining_resources <= 0:
            return "⏱️ 0 sec restantes"

        # Estimate remaining time
        estimated_seconds = avg_time_per_resource * remaining_resources
        estimated_minutes = estimated_seconds / 60

        # Format output based on time magnitude
        if estimated_minutes < 1:
            return f"⏱️ ~{estimated_seconds:.0f} sec restantes"
        elif estimated_minutes < 60:
            return f"⏱️ ~{estimated_minutes:.1f} min restantes"
        else:
            # For very long times, show hours
            estimated_hours = estimated_minutes / 60
            return f"⏱️ ~{estimated_hours:.1f} h restantes"

    @staticmethod
    def save_course_hierarchy_to_db(course_name: str):
        """Save course hierarchy to database."""
        if not ChatbotFront.api_client:
            st.error("❌ Impossible de démarrer le scraping : API client non initialisé")
            return
        course = CourseLoader.load_course_structure(course_name)
        asyncio.run(ChatbotFront.api_client.acreate_course_from_hierarchy(course.to_dict()))
        st.success("✅ Hiérarchie du parcours persistée en base avec succès.")

    @staticmethod
    def scrape_parcour_all_courses_opale(parcour_name: str):
        """Scrape all courses from a parcours with real-time progress display."""
        import json
        import os

        # Check if API client is initialized
        if not ChatbotFront.api_client:
            st.error("❌ Impossible de démarrer le scraping : API client non initialisé")
            return

        analysed_course_file_path = f"outputs/{parcour_name}.json"
        if not os.path.exists(analysed_course_file_path):
            st.error(f"❌ Fichier non trouvé : {analysed_course_file_path}")
            return

        with open(analysed_course_file_path, encoding="utf-8") as analysed_json_file:
            loaded_analysed_parcour_json = json.load(analysed_json_file)

        # Create async function to handle streaming
        async def scrape_with_progress():
            """Handle scraping with real-time progress updates."""
            import time

            # Create a prominent header for the scraping operation
            st.markdown("---")
            st.markdown("### 🚀 Scraping en cours")

            # Create placeholder for progress display
            progress_container = st.empty()
            status_container = st.empty()

            # Initialize progress tracking
            total_resources = 0
            current = 0
            successful = 0
            skipped = 0
            failed = 0
            start_time = None

            try:
                # Consume the SSE stream
                async for event in ChatbotFront.api_client.ascrape_parcour_all_courses_streaming(
                    loaded_analysed_parcour_json
                ):
                    event_type = event.get("event")

                    if event_type == "started":
                        # Initialize progress bar with total count and start timer
                        total_resources = event.get("total_resources", 0)
                        start_time = time.time()
                        progress_container.progress(0, text=f"Démarrage du scraping de {total_resources} ressources...")
                        status_container.info(f"📦 Parcours: **{event.get('parcours_name')}**")

                    elif event_type == "progress":
                        # Update progress bar
                        current = event.get("current", 0)
                        total = event.get("total", 1)
                        resource = event.get("resource", {})

                        # Calculate progress percentage
                        progress_percent = current / total if total > 0 else 0

                        # Update counters based on resource status
                        resource_status = resource.get("status", "")
                        if resource_status == "success":
                            successful += 1
                            emoji = "✅"
                        elif resource_status == "skipped":
                            skipped += 1
                            emoji = "⏭️"
                        else:  # failed
                            failed += 1
                            emoji = "❌"

                        # Update progress bar with current status
                        progress_text = f"**{current}/{total}** - {emoji} {resource.get('name', 'Unknown')}"
                        with progress_container:
                            st.progress(progress_percent, text=progress_text)

                        # Calculate estimated remaining time
                        if start_time:
                            estimated_time = ChatbotFront.calculate_estimated_time_remaining(
                                start_time, successful, total_resources, current
                            )
                        else:
                            estimated_time = ""

                        # Update status with detailed counters and estimated time
                        with status_container:
                            st.info(
                                f"🔄 En cours... | ✅ Réussis: **{successful}** | ⏭️ Skippés: **{skipped}** | ❌ Échecs: **{failed}** | {estimated_time}"
                            )

                    elif event_type == "completed":
                        # Final summary
                        progress_container.progress(
                            1.0, text=f"✅ Terminé! {current}/{total_resources} ressources traitées"
                        )

                        final_status = event.get("status", "")
                        successful_count = event.get("successful", 0)
                        skipped_count = event.get("skipped", 0)
                        failed_count = event.get("failed", 0)

                        if final_status == "success":
                            status_container.success(
                                f"🎉 **Scraping terminé avec succès!**\n\n"
                                f"✅ Réussis: **{successful_count}** | "
                                f"⏭️ Skippés: **{skipped_count}** | "
                                f"❌ Échecs: **{failed_count}**"
                            )
                        elif final_status == "partial_success":
                            status_container.warning(
                                f"⚠️ **Scraping terminé avec quelques problèmes**\n\n"
                                f"✅ Réussis: **{successful_count}** | "
                                f"⏭️ Skippés: **{skipped_count}** | "
                                f"❌ Échecs: **{failed_count}**"
                            )
                        else:  # error
                            status_container.error(
                                f"💥 **Scraping échoué**\n\n"
                                f"✅ Réussis: **{successful_count}** | "
                                f"⏭️ Skippés: **{skipped_count}** | "
                                f"❌ Échecs: **{failed_count}**"
                            )

                        # Show a balloon animation for successful completion
                        if final_status == "success":
                            st.balloons()

                    elif event_type == "error":
                        # Critical error occurred
                        progress_container.empty()
                        status_container.error(f"💥 **Erreur critique:** {event.get('message', 'Unknown error')}")

            except Exception as e:
                progress_container.empty()
                status_container.error(f"💥 **Erreur lors du scraping:** {e}")

        # Run the async scraping with progress display
        asyncio.run(scrape_with_progress())

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
            if st.button("🔄 Réessayer la connexion API"):
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

    @staticmethod
    def apply_custom_css() -> None:
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
