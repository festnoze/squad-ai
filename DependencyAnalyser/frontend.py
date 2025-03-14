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

# Fonction pour regrouper hiérarchiquement les modules
def group_modules_hierarchically(modules, project_name):
    # Dictionnaire pour stocker la structure hiérarchique
    hierarchy = {}
    
    # Construction de la structure hiérarchique
    for module in modules:
        # Supprimer la duplication du nom du projet au début
        if module.startswith(f"{project_name}.{project_name}."):
            # Retirer le premier [project_name]. du module
            module = module[len(project_name)+1:]
        
        parts = module.split('.')
        current_level = hierarchy
        for i, part in enumerate(parts):
            # Création du chemin jusqu'à ce niveau
            path_to_here = '.'.join(parts[:i+1])
            
            # Initialisation du niveau s'il n'existe pas
            if part not in current_level:
                current_level[part] = {
                    'full_path': path_to_here,
                    'children': {},
                    'is_leaf': (i == len(parts) - 1)
                }
            elif i == len(parts) - 1:
                # Mise à jour si c'est une feuille
                current_level[part]['is_leaf'] = True
                
            # Progression au niveau suivant
            current_level = current_level[part]['children']
    
    return hierarchy

# Fonction pour afficher la structure hiérarchique dans Streamlit avec indentation
def display_hierarchy(hierarchy, indent=0, parent_path="", project_name=""):
    # Trier les clés pour un affichage cohérent
    sorted_keys = sorted(hierarchy.keys())
    
    for key in sorted_keys:
        node = hierarchy[key]
        full_path = node['full_path']
        children = node['children']
        is_leaf = node['is_leaf']
        
        # Déterminer quel texte afficher
        if children:  # Nœud avec enfants
            # Simplifier l'affichage en utilisant *
            display_text = f"{full_path}.*"
            st.markdown("&nbsp;" * (indent * 2) + f"- **{display_text}**")
            
            # Afficher les enfants avec indentation supplémentaire
            display_hierarchy(children, indent + 1, full_path, project_name)
        elif is_leaf:  # Feuille sans enfants
            # Afficher le module individuel si ce n'est pas déjà couvert par un parent
            if not parent_path or not full_path.startswith(parent_path):
                # Utiliser *.module_name si le module est profondément niché
                if parent_path:
                    # Extraire le dernier segment du chemin complet
                    last_segment = full_path.split('.')[-1]
                    display_text = f"*.{last_segment}"
                else:
                    display_text = full_path
                st.markdown("&nbsp;" * (indent * 2) + f"- *{display_text}*")

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
    
    # Affichage des détails des sous-librairies avec regroupement hiérarchique
    st.header("Détails des sous-librairies")
    
    # Présentation sur une seule colonne avec éléments collapsables (fermés par défaut)
    for g_id in sorted(list(groups)):
        members = [m for m, grp in analyzer.module_to_group.items() if grp == g_id]
        
        # Créer un élément expansible (fermé par défaut)
        with st.expander(f"Sous-librairie {g_id}", expanded=False):
            # Utilisation du regroupement hiérarchique pour l'affichage
            hierarchy = group_modules_hierarchically(sorted(members), project_name)
            display_hierarchy(hierarchy, project_name=project_name)
