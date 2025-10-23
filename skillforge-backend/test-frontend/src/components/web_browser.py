"""Web browser component for displaying course resources."""

import streamlit as st
import streamlit.components.v1 as components


def render_web_browser() -> None:
    """Render the web browser iframe for displaying resources."""
    selected_ro = st.session_state.get("selected_ressource_object")

    if not selected_ro:
        st.info("👈 Select a resource from the sidebar to view it here.")
        st.markdown(
            """
            ### How to use:
            1. Select a **Course** from the sidebar
            2. Navigate through **Matiere** → **Module** → **Theme** → **Resource**
            3. The resource will appear here
            4. Use the AI Assistant to ask questions about the content
            """
        )
        return

    # Display resource information
    st.markdown(f"**Resource:** {selected_ro.name}")
    st.markdown(f"**Type:** `{selected_ro.type}`")

    # Display resource in iframe
    if selected_ro.url:
        st.markdown("---")
        try:
            # Use Streamlit's native iframe component
            components.iframe(src=selected_ro.url, height=600, scrolling=True)
        except Exception as e:
            st.error(f"Failed to load resource: {e}")
            st.markdown(f"**Resource URL:** {selected_ro.url}")
            st.markdown("You can try opening the link manually.")
    else:
        st.warning("No URL available for this resource.")
