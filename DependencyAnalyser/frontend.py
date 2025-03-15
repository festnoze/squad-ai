import streamlit as st
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import networkx as nx

from dependency_analyser import DependencyAnalyzer

st.title("Analyseur de dépendances pour projet Python")
analyzer = None
groups = None

# CSS pour personnaliser les expandeurs et ajouter les tooltips
def init_custom_css():
    st.markdown("""
    <style>
    .no-border {
        border: none !important;
        box-shadow: none !important;
        background-color: transparent !important;
    }
    .no-border .streamlit-expanderHeader {
        background-color: transparent !important;
        font-weight: bold;
    }
    .no-border .streamlit-expanderContent {
        border: none !important;
        padding-left: 20px !important;
    }
    
    /* Style pour les tooltips au survol */
    .tooltip {
        position: relative;
        display: inline-block;
        cursor: pointer;
    }
    
    .tooltip .tooltiptext {
        visibility: hidden;
        width: auto;
        background-color: #f1f1f1;
        color: #333;
        text-align: left;
        border-radius: 6px;
        padding: 8px;
        position: absolute;
        z-index: 1;
        bottom: 125%;
        left: 0;
        margin-left: 0;
        opacity: 0;
        transition: opacity 0.3s;
        box-shadow: 0px 2px 4px rgba(0,0,0,0.2);
        font-size: 14px;
        white-space: nowrap;
    }
    
    .tooltip:hover .tooltiptext {
        visibility: visible;
        opacity: 1;
    }
    </style>
    """, unsafe_allow_html=True)

# Initialiser le CSS personnalisé
init_custom_css()

# Configuration dans la barre latérale
with st.sidebar:
    project_path = st.text_input("Chemin vers le projet", value="C:/Dev/IA/CommonTools")
    project_name = st.text_input("Nom du package Python", value="common_tools")
    granularity = st.slider("Granularité", min_value=2, max_value=50, value=10, step=1)
    
    with st.expander("Options avancées"):
        splitable_folders_input = st.text_input(
            "Dossiers divisibles (séparés par des virgules)", 
            value="helpers",
            help="Ces dossiers peuvent être divisés entre différentes sous-librairies"
        )
        splitable_folders = [folder.strip() for folder in splitable_folders_input.split(",") if folder.strip()]

    if st.button("Analyser"):
        analyzer = DependencyAnalyzer(project_path, project_name, splitable_folders)
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

# Fonction pour afficher la structure hiérarchique dans Streamlit
def display_hierarchy(hierarchy, indent=0, parent_path="", project_name=""):
    # Trier les clés pour un affichage cohérent
    sorted_keys = sorted(hierarchy.keys())
    
    for key in sorted_keys:
        node = hierarchy[key]
        full_path = node['full_path']
        children = node['children']
        is_leaf = node['is_leaf']
        
        # Indentation basée sur le niveau
        padding = indent * 20
        
        # Toujours afficher ce nœud, qu'il ait des enfants ou non
        if children or is_leaf:
            # Vérifier si ce nœud est l'avant-dernier niveau (a des enfants feuilles)
            has_leaf_children_only = all(child['is_leaf'] and not child['children'] for child in children.values()) if children else False
            
            # Si c'est l'avant-dernier niveau (a uniquement des enfants feuilles)
            if has_leaf_children_only and children:
                # Collecter tous les modules feuilles pour le tooltip
                leaf_modules = [child['full_path'] for child in children.values()]
                
                # Formater le texte du tooltip
                tooltip_content = "<br>".join([f"- {leaf}" for leaf in sorted(leaf_modules)])
                
                # Afficher avec tooltip contenant les feuilles
                st.markdown(f"""
                <div style="margin-left: {padding}px;" class="tooltip">
                  <span><b>{full_path}.*</b></span>
                  <span class="tooltiptext">{tooltip_content}</span>
                </div>
                """, unsafe_allow_html=True)
            
            # Pour les niveaux intermédiaires
            elif children and not has_leaf_children_only:
                # Afficher ce nœud normalement
                st.markdown(f"<div style='margin-left: {padding}px;'><b>{full_path}.*</b></div>", unsafe_allow_html=True)
                
                # Afficher récursivement les enfants (sauf si ce sont des feuilles)
                display_hierarchy(children, indent + 1, full_path, project_name)
            
            # Si c'est une feuille sans enfants et pas au premier niveau, ne pas l'afficher
            # (ils seront dans les tooltips du niveau parent)
            elif is_leaf and not children and indent > 0:
                continue
            
            # Si c'est une feuille au premier niveau (sans parent)
            elif is_leaf and not children and indent == 0:
                st.markdown(f"<div style='margin-left: {padding}px;'><i>{full_path}</i></div>", unsafe_allow_html=True)

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
