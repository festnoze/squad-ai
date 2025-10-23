"""Chat component for AI assistant interaction."""

import asyncio

import streamlit as st

from src.api.skillforge_client import build_course_context


def render_chat() -> None:
    """Render the chat interface with AI assistant."""
    selected_ro = st.session_state.get("selected_ressource_object")

    if not selected_ro:
        st.info("👈 Select a resource from the sidebar to start chatting.")
        return

    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input
    if prompt := st.chat_input("Ask me anything about the resource..."):
        # Add user message to chat
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Get or create thread for current context
        if not st.session_state.current_thread_id:
            with st.spinner("Initializing conversation..."):
                try:
                    thread_id = asyncio.run(_get_or_create_thread())
                    st.session_state.current_thread_id = thread_id
                except Exception as e:
                    st.error(f"Failed to initialize conversation: {e}")
                    return

        # Generate AI response
        with st.chat_message("assistant"):
            response_placeholder = st.empty()
            full_response = ""

            try:
                # Stream the AI response
                api_client = st.session_state.api_client
                thread_id = st.session_state.current_thread_id

                # Build course context
                course_context = _build_current_course_context()

                # Use asyncio to run the streaming function
                async def stream_response():
                    nonlocal full_response
                    async for chunk in api_client.asend_query_streaming(thread_id, prompt, course_context):
                        full_response += chunk
                        response_placeholder.markdown(full_response + "▌")

                asyncio.run(stream_response())
                response_placeholder.markdown(full_response)

                # Add assistant response to chat history
                st.session_state.messages.append({"role": "assistant", "content": full_response})

            except Exception as e:
                error_msg = f"Error generating response: {e}"
                response_placeholder.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})


async def _get_or_create_thread() -> str:
    """Get or create a thread for the current resource context."""
    api_client = st.session_state.api_client
    course_context = _build_current_course_context()

    thread_id = await api_client.aget_or_create_thread(course_context)
    return thread_id


def _build_current_course_context() -> dict:
    """Build course context from current session state."""
    selected_ro = st.session_state.selected_ressource_object
    selected_theme = st.session_state.selected_theme
    selected_module = st.session_state.selected_module
    selected_matiere = st.session_state.selected_matiere
    course = st.session_state.selected_course_content

    return build_course_context(
        ressource_id=selected_ro.id if selected_ro else None,
        ressource_type=selected_ro.type if selected_ro else None,
        ressource_code=None,  # Not available in our model
        ressource_title=selected_ro.name if selected_ro else None,
        ressource_url=selected_ro.url if selected_ro else None,
        theme_id=selected_theme.id if selected_theme else None,
        module_id=selected_module.id if selected_module else None,
        matiere_id=selected_matiere.id if selected_matiere else None,
        parcour_id=course.parcours_id if course else None,
        parcours_name=course.name if course else None,
    )
