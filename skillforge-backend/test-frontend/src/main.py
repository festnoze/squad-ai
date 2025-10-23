"""SkillForge Frontend - Main Streamlit application entry point."""

import streamlit as st


def init_session_state() -> None:
    """Initialize Streamlit session state variables."""
    # Chat messages
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Thread management
    if "current_thread_id" not in st.session_state:
        st.session_state.current_thread_id = None

    # Course selection
    if "selected_course_name" not in st.session_state:
        st.session_state.selected_course_name = None

    if "selected_course_content" not in st.session_state:
        st.session_state.selected_course_content = None

    # Navigation state
    if "selected_matiere" not in st.session_state:
        st.session_state.selected_matiere = None

    if "selected_module" not in st.session_state:
        st.session_state.selected_module = None

    if "selected_theme" not in st.session_state:
        st.session_state.selected_theme = None

    if "selected_ressource_object" not in st.session_state:
        st.session_state.selected_ressource_object = None

    # API client
    if "api_client" not in st.session_state:
        try:
            st.session_state.api_client = None  # SkillForgeClient()
        except ValueError as e:
            st.error(f"Failed to initialize API client: {e}")
            st.stop()


def apply_custom_styles() -> None:
    """Apply custom CSS styles to the Streamlit app."""
    st.markdown(
        """
        <style>
        /* Hide Streamlit branding */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}

        /* Adjust sidebar - force visibility and size */
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

        /* Ensure sidebar is visible */
        section[data-testid="stSidebar"][aria-expanded="true"] {
            display: block !important;
            visibility: visible !important;
            transform: translateX(0) !important;
        }

        /* Override any Streamlit classes that hide the sidebar */
        .st-emotion-cache-1k02nrb {
            transform: translateX(0) !important;
        }

        /* Improve spacing */
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }

        /* Style chat messages */
        .stChatMessage {
            padding: 1rem;
            margin-bottom: 0.5rem;
            border-radius: 0.5rem;
        }

        /* Style resource viewer */
        .resource-viewer {
            border: 1px solid #ddd;
            border-radius: 0.5rem;
            padding: 1rem;
            margin-bottom: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    """Main application entry point."""
    # Page configuration
    st.set_page_config(
        page_title="SkillForge - AI Learning Assistant",
        page_icon="🎓",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Initialize session state
    init_session_state()

    # Apply custom styles
    apply_custom_styles()

    # Title
    st.title("🎓 SkillForge - AI Learning Assistant")

    # Import components here to avoid circular imports
    from src.components.chat import render_chat
    from src.components.sidebar import render_sidebar
    from src.components.web_browser import render_web_browser

    # Sidebar
    with st.sidebar:
        render_sidebar()

    # Main content area
    # Create two columns: web browser and chat
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("📚 Resource Viewer")
        render_web_browser()

    with col2:
        st.subheader("💬 AI Assistant")
        render_chat()


if __name__ == "__main__":
    main()
