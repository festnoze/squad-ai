import streamlit as st
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import networkx as nx
import json
import os
from pathlib import Path
import shutil
import tempfile
from streamlit.components.v1 import html

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
    granularity = st.slider("Granularité", min_value=2, max_value=50, value=10, step=1, 
                           help="Nombre cible de sous-librairies à créer")

    with st.expander("Options avancées"):
        splitable_folders_input = st.text_input(
            "Dossiers divisibles (séparés par des virgules)", 
            value="helpers",
            help="Ces dossiers peuvent être divisés entre différentes sous-librairies"
        )
        splitable_folders = [folder.strip() for folder in splitable_folders_input.split(",") if folder.strip()]
        
        show_detailed_report = st.checkbox("Afficher le rapport détaillé", value=True,
                                           help="Montrer les détails complets des sous-librairies")

    if st.button("Analyser"):
        with st.spinner("Analyse en cours..."):
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
    # Onglets principaux pour les différentes vues
    tab1, tab2, tab3 = st.tabs(["Visualisation", "Détails des sous-librairies", "Rapport"])
    
    with tab1:
        st.header("Graphe de dépendances entre sous-librairies")
        
        # Vérifier que les fichiers de visualisation sont disponibles
        js_file = Path("static/dependency_graph.js")
        html_file = Path("static/dependency_graph.html")
        
        if not js_file.exists() or not html_file.exists():
            st.error("Fichiers de visualisation non trouvés. Assurez-vous que les fichiers static/dependency_graph.js et static/dependency_graph.html existent.")
        else:
            # Obtenir les données du graphe au format JSON
            graph_data = analyzer.get_graph_json_data()
            graph_data_json = json.dumps(graph_data)
            
            # Créer le HTML autonome pour la visualisation
            standalone_html = f"""
            <!DOCTYPE html>
            <html lang="fr">
            <head>
                <meta charset="UTF-8">
                <title>Visualisation des dépendances</title>
                <script src="https://d3js.org/d3.v7.min.js"></script>
                <script>
                {open(js_file, "r").read()}
                
                document.addEventListener('DOMContentLoaded', function() {{
                    const graphData = {graph_data_json};
                    createDependencyGraph('graph-container', graphData, {{
                        width: 800,
                        height: 600,
                        nodeMinSize: 40,
                        nodeMaxSize: 120,
                        fontMinSize: 14,
                        fontMaxSize: 20,
                        fontActiveSize: 24
                    }});
                }});
                </script>
                <style>
                    body {{
                        margin: 0;
                        padding: 0;
                        overflow: hidden;
                    }}
                    #graph-container {{
                        width: 100%;
                        height: 100vh;
                        background-color: #f5f5f5;
                    }}
                </style>
            </head>
            <body>
                <div id="graph-container"></div>
            </body>
            </html>
            """
            
            # Afficher la visualisation directement
            st.components.v1.html(standalone_html, height=600)
            
            st.caption(f"Structure des sous-librairies (granularité: {len(groups)}). Cliquez sur une libraire pour zoomer.")
            
            with st.expander("Instructions d'utilisation"):
                st.markdown("""
                - **Cliquez sur un nœud** pour le mettre en évidence avec ses connexions
                - **Cliquez à nouveau** sur un nœud sélectionné pour annuler la sélection
                - **Faites glisser un nœud** pour ajuster manuellement la disposition
                - **Utilisez la molette de la souris** pour zoomer et dézoomer
                - **Cliquez et faites glisser l'arrière-plan** pour vous déplacer dans le graphique
                """)
            
            # Option pour télécharger la visualisation
            st.download_button(
                "Télécharger la visualisation interactive",
                standalone_html,
                "dependency_graph.html",
                "text/html"
            )
    
    with tab2:
        st.header("Détails des sous-librairies")
        
        # Statistiques générales
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Nombre de sous-librairies", len(groups))
        with col2:
            st.metric("Nombre de fichiers Python", len(analyzer.python_files))
        with col3:
            avg_size = len(analyzer.python_files) / len(groups) if groups else 0
            st.metric("Taille moyenne", f"{avg_size:.1f} fichiers")
        
        st.markdown("---")
        
        # Présentation sur une seule colonne avec éléments collapsables
        for g_id in sorted(list(groups)):
            members = [m for m, grp in analyzer.module_to_group.items() if grp == g_id]
            
            # Collecter des statistiques pour cette sous-librairie
            ext_deps = set()
            for module in members:
                if module in analyzer.dependencies:
                    ext_deps.update(analyzer.dependencies[module]['external'])
            
            # Créer un élément expansible
            with st.expander(f"Sous-librairie {g_id} ({len(members)} modules, {len(ext_deps)} dépendances externes)", expanded=False):
                # Affichage de la liste complète des modules
                st.subheader("Modules")
                
                # Créer une liste scrollable de modules si la liste est longue
                if len(members) > 10:
                    with st.container():
                        scroll_container = st.empty()
                        with scroll_container.container():
                            st.write('\n'.join([f"- `{m.replace(project_name+'.', '')}`" for m in sorted(members)]))
                else:
                    # Affichage simple pour peu de modules
                    for m in sorted(members):
                        st.markdown(f"- `{m.replace(project_name+'.', '')}`")
                
                st.markdown("---")
                
                # Organisation en colonnes pour structure et dépendances
                subcol1, subcol2 = st.columns([2, 3])
                
                with subcol1:
                    st.subheader("Structure hiérarchique")
                    hierarchy = group_modules_hierarchically(sorted(members), project_name)
                    display_hierarchy(hierarchy, project_name=project_name)
                
                with subcol2:
                    st.subheader("Dépendances externes")
                    if ext_deps:
                        for dep in sorted(ext_deps):
                            st.markdown(f"- `{dep}`")
                    else:
                        st.info("Aucune dépendance externe")
    
    with tab3:
        st.header("Rapport détaillé")
        
        if show_detailed_report:
            report = analyzer.print_sub_libraries_info()
            st.markdown(report)
        else:
            st.info("Activer 'Afficher le rapport détaillé' dans les options avancées pour voir le rapport complet.")
