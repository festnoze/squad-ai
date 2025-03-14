import streamlit as st
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import networkx as nx

from dependency_analyser import DependencyAnalyzer

st.title("Analyseur de dépendances pour projet Python")
analyzer = None
groups = None

# Configuration dans la barre latérale
with st.sidebar:
    project_path = st.text_input("Chemin vers le projet", value="C:/Dev/IA/CommonTools")
    project_name = st.text_input("Nom du package Python", value="common_tools")
    granularity = st.slider("Granularité", min_value=2, max_value=50, value=10, step=1)

    if st.button("Analyser"):
        analyzer = DependencyAnalyzer(project_path, project_name)
        analyzer.find_python_files()
        analyzer.extract_imports()
        analyzer.analyze_dependency_structure()
        analyzer.partition_by_granularity(granularity)
        groups = set(analyzer.module_to_group.values())
        st.sidebar.write(f"Nombre de sous-librairies détectées: {len(groups)}")

# Affichage des résultats dans la fenêtre principale
if analyzer and groups:
    # Affichage du graphe de dépendances
    st.header("Graphe de dépendances entre sous-librairies")
    sub_lib_graph = analyzer.grouped_graph
    fig, ax = plt.subplots(figsize=(10, 8))
    pos = nx.spring_layout(sub_lib_graph, k=0.3)
    nx.draw_networkx_nodes(sub_lib_graph, pos, node_color='cyan', node_size=700, ax=ax)
    nx.draw_networkx_edges(sub_lib_graph, pos, arrows=True, ax=ax)
    labels = {n: f"Lib {n}" for n in sub_lib_graph.nodes()}
    nx.draw_networkx_labels(sub_lib_graph, pos, labels=labels, font_size=10, ax=ax)
    plt.title("Sous-librairies (Dépendances inter-libs)")
    plt.axis('off')
    st.pyplot(fig)
    
    # Affichage des détails des sous-librairies
    st.header("Détails des sous-librairies")
    cols = st.columns(min(3, len(groups)))
    for i, g_id in enumerate(sorted(list(groups))):
        with cols[i % len(cols)]:
            members = [m for m, grp in analyzer.module_to_group.items() if grp == g_id]
            st.markdown(f"### Sous-librairie {g_id}")
            for m in sorted(members):
                st.write(m)
