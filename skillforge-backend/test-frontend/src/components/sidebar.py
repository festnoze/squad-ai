"""Sidebar component for course navigation."""

import streamlit as st

from src.utils.course_loader import CourseLoader


def render_sidebar() -> None:
    """Render the sidebar with course navigation."""
    st.header("📖 Course Navigation")

    # Course selection
    available_courses = CourseLoader.load_available_courses()

    if not available_courses:
        st.warning("No courses found in outputs/ directory. Please add course JSON files.")
        return

    selected_course_name = st.selectbox(
        "Select Course",
        options=available_courses,
        index=0 if available_courses else None,
        key="course_selector",
    )

    # Load course structure if selection changed
    if selected_course_name != st.session_state.selected_course_name:
        try:
            st.session_state.selected_course_content = CourseLoader.load_course_structure(selected_course_name)
            st.session_state.selected_course_name = selected_course_name

            # Reset navigation state
            st.session_state.selected_matiere = None
            st.session_state.selected_module = None
            st.session_state.selected_theme = None
            st.session_state.selected_ressource_object = None
            st.session_state.current_thread_id = None
            st.session_state.messages = []

            st.rerun()
        except Exception as e:
            st.error(f"Failed to load course: {e}")
            return

    # Show hierarchical navigation if course is loaded
    if st.session_state.selected_course_content:
        course = st.session_state.selected_course_content

        st.divider()

        # Matiere selection
        matieres = CourseLoader.get_matieres(course)
        if matieres:
            matiere_options = {f"{m.name} ({m.code})": m for m in matieres}
            selected_matiere_key = st.selectbox(
                "📚 Matiere (Subject)",
                options=list(matiere_options.keys()),
                index=0 if matiere_options else None,
                key="matiere_selector",
            )

            if selected_matiere_key:
                selected_matiere = matiere_options[selected_matiere_key]

                # Check if matiere changed
                if selected_matiere != st.session_state.selected_matiere:
                    st.session_state.selected_matiere = selected_matiere
                    st.session_state.selected_module = None
                    st.session_state.selected_theme = None
                    st.session_state.selected_ressource_object = None

                # Module selection
                modules = CourseLoader.get_modules(selected_matiere)
                if modules:
                    module_options = {f"{m.name} ({m.code})": m for m in modules}
                    selected_module_key = st.selectbox(
                        "📂 Module",
                        options=list(module_options.keys()),
                        index=0 if module_options else None,
                        key="module_selector",
                    )

                    if selected_module_key:
                        selected_module = module_options[selected_module_key]

                        # Check if module changed
                        if selected_module != st.session_state.selected_module:
                            st.session_state.selected_module = selected_module
                            st.session_state.selected_theme = None
                            st.session_state.selected_ressource_object = None

                        # Theme selection
                        themes = CourseLoader.get_themes(selected_module)
                        if themes:
                            theme_options = {f"{t.name} ({t.code})": t for t in themes}
                            selected_theme_key = st.selectbox(
                                "📑 Theme",
                                options=list(theme_options.keys()),
                                index=0 if theme_options else None,
                                key="theme_selector",
                            )

                            if selected_theme_key:
                                selected_theme = theme_options[selected_theme_key]

                                # Check if theme changed
                                if selected_theme != st.session_state.selected_theme:
                                    st.session_state.selected_theme = selected_theme
                                    st.session_state.selected_ressource_object = None

                                # Ressource selection
                                ressources = CourseLoader.get_ressources(selected_theme)
                                if ressources:
                                    # Get all resource objects from all ressources
                                    all_ressource_objects = []
                                    for ressource in ressources:
                                        ressource_objects = CourseLoader.get_ressource_objects(ressource)
                                        all_ressource_objects.extend(ressource_objects)

                                    if all_ressource_objects:
                                        ro_options = {f"{ro.name} [{ro.type}]": ro for ro in all_ressource_objects}
                                        selected_ro_key = st.selectbox(
                                            "📄 Resource",
                                            options=list(ro_options.keys()),
                                            index=0 if ro_options else None,
                                            key="ressource_object_selector",
                                        )

                                        if selected_ro_key:
                                            selected_ro = ro_options[selected_ro_key]

                                            # Check if resource changed
                                            if selected_ro != st.session_state.selected_ressource_object:
                                                st.session_state.selected_ressource_object = selected_ro
                                                # Reset thread and messages when resource changes
                                                st.session_state.current_thread_id = None
                                                st.session_state.messages = []
                                    else:
                                        st.info("No resource objects available for this theme.")
                                else:
                                    st.info("No resources available for this theme.")
                        else:
                            st.info("No themes available for this module.")
                else:
                    st.info("No modules available for this matiere.")
        else:
            st.info("No matieres available for this course.")

        st.divider()

        # Action buttons
        if st.button("🗑️ Clear Conversation", use_container_width=True):
            st.session_state.messages = []
            st.session_state.current_thread_id = None
            st.rerun()

        # Display current selection info
        if st.session_state.selected_ressource_object:
            st.success("✅ Resource loaded! You can now chat about it.")
            with st.expander("Current Selection"):
                st.write(f"**Course:** {course.name}")
                if st.session_state.selected_matiere:
                    st.write(f"**Matiere:** {st.session_state.selected_matiere.name}")
                if st.session_state.selected_module:
                    st.write(f"**Module:** {st.session_state.selected_module.name}")
                if st.session_state.selected_theme:
                    st.write(f"**Theme:** {st.session_state.selected_theme.name}")
                if st.session_state.selected_ressource_object:
                    st.write(f"**Resource:** {st.session_state.selected_ressource_object.name}")
