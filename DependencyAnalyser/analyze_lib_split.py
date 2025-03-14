import os
import sys
import ast
import argparse
import networkx as nx
import matplotlib.pyplot as plt
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

class ImportVisitor(ast.NodeVisitor):
    """Visiteur AST pour extraire les imports d'un fichier Python."""
    
    def __init__(self):
        self.imports = set()
        self.from_imports = {}
    
    def visit_Import(self, node):
        for alias in node.names:
            self.imports.add(alias.name)
    
    def visit_ImportFrom(self, node):
        if node.module is not None:  # Pour gérer "from . import x"
            module_path = node.module
            if node.level > 0:
                # Import relatif, mais nous ne pouvons pas le résoudre sans contexte
                module_path = '.' * node.level + module_path
            
            for alias in node.names:
                if module_path in self.from_imports:
                    self.from_imports[module_path].add(alias.name)
                else:
                    self.from_imports[module_path] = {alias.name}

class DependencyAnalyzer:
    """Analyseur de dépendances pour restructurer une bibliothèque Python."""
    
    def __init__(self, project_path: str, project_name: str):
        self.project_path = Path(project_path).resolve()
        self.project_name = project_name
        self.python_files = {}  # {path: module_name}
        self.dependencies = {}  # {module_name: {internal_deps}, {external_deps}}
        self.dependency_graph = nx.DiGraph()
        self.module_groups = {}
    
    def find_python_files(self):
        """Trouve tous les fichiers Python dans le projet."""
        print(f"Recherche des fichiers Python dans {self.project_path}")
        for root, _, files in os.walk(self.project_path):
            for file in files:
                if file.endswith('.py'):
                    file_path = Path(root) / file
                    rel_path = file_path.relative_to(self.project_path)
                    
                    # Convertir le chemin du fichier en un nom de module Python
                    if file == "__init__.py":
                        module_path = str(rel_path.parent).replace(os.sep, '.')
                        if module_path == '.':
                            module_path = self.project_name
                        else:
                            module_path = f"{self.project_name}.{module_path}"
                    else:
                        module_path = str(rel_path.with_suffix('')).replace(os.sep, '.')
                        if module_path.startswith('.'):
                            module_path = f"{self.project_name}{module_path}"
                        else:
                            module_path = f"{self.project_name}.{module_path}"
                    
                    self.python_files[file_path] = module_path
        
        print(f"Trouvé {len(self.python_files)} fichiers Python")
    
    def extract_imports(self):
        """Extrait les imports de chaque fichier Python."""
        print("Extraction des imports...")
        for file_path, module_name in self.python_files.items():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    tree = ast.parse(f.read(), filename=str(file_path))
                
                visitor = ImportVisitor()
                visitor.visit(tree)
                
                # Déterminer quels imports sont internes au projet
                internal_deps = set()
                external_deps = set()
                
                # Traiter les imports directs
                for imp in visitor.imports:
                    if imp == self.project_name or imp.startswith(f"{self.project_name}."):
                        internal_deps.add(imp)
                    else:
                        external_deps.add(imp)
                
                # Traiter les imports from
                for module, names in visitor.from_imports.items():
                    if module == self.project_name or module.startswith(f"{self.project_name}."):
                        internal_deps.add(module)
                    else:
                        external_deps.add(module)
                
                self.dependencies[module_name] = {
                    'internal': internal_deps,
                    'external': external_deps
                }
                
                # Ajouter au graphe de dépendances
                self.dependency_graph.add_node(module_name)
                for dep in internal_deps:
                    self.dependency_graph.add_edge(module_name, dep)
                
            except Exception as e:
                print(f"Erreur lors de l'analyse de {file_path}: {e}")
        
        print(f"Extraction des imports terminée pour {len(self.dependencies)} modules")
    
    def analyze_dependency_structure(self):
        """Analyse la structure des dépendances et identifie les groupes potentiels."""
        print("Analyse de la structure des dépendances...")
        
        # Identifier les modules sans dépendances internes
        standalone_modules = []
        for module, deps in self.dependencies.items():
            if not deps['internal']:
                standalone_modules.append(module)
        
        # Identifier les composants fortement connectés (cycles de dépendances)
        sccs = list(nx.strongly_connected_components(self.dependency_graph))
        
        # Regrouper les modules par dépendances externes communes
        external_dep_groups = defaultdict(list)
        for module, deps in self.dependencies.items():
            # Créer une clé hashable à partir des dépendances externes
            ext_deps_key = frozenset(deps['external'])
            external_dep_groups[ext_deps_key].append(module)
        
        # Organisation des résultats
        self.module_groups = {
            'standalone': standalone_modules,
            'cycles': sccs,
            'by_external_deps': dict(external_dep_groups)
        }
        
        print(f"Modules autonomes: {len(standalone_modules)}")
        print(f"Composants fortement connectés: {len(sccs)}")
        print(f"Groupes par dépendances externes: {len(external_dep_groups)}")
    
    def suggest_packages(self):
        """Suggère une structure de packages basée sur l'analyse des dépendances."""
        print("\nSuggestion de structure de packages:")
        
        # Construire un graphe de dépendances condensé (où chaque SCC est un seul nœud)
        condensed_graph = nx.condensation(self.dependency_graph)
        
        # Trier les composants dans un ordre topologique
        component_order = list(nx.topological_sort(condensed_graph))
        
        # Créer des packages basés sur les niveaux de dépendance et les groupes externes
        proposed_packages = {}
        
        # 1. Les modules autonomes forment leurs propres packages de base
        base_packages = self.module_groups['standalone']
        if base_packages:
            proposed_packages['base'] = base_packages
            print("\n1. Package de base (sans dépendances internes):")
            for module in sorted(base_packages):
                print(f"  - {module}")
        
        # 2. Regrouper les cycles comme des packages atomiques
        cycle_packages = {}
        for i, cycle in enumerate(self.module_groups['cycles']):
            if len(cycle) > 1:  # Ignorer les cycles à un seul élément
                cycle_name = f"cycle_{i+1}"
                cycle_packages[cycle_name] = list(cycle)
                print(f"\n2. Package de cycle {i+1} (dépendances circulaires):")
                for module in sorted(cycle):
                    print(f"  - {module}")
        
        # 3. Regrouper par dépendances externes communes
        ext_packages = {}
        for i, (ext_deps, modules) in enumerate(self.module_groups['by_external_deps'].items()):
            if len(modules) > 1 and ext_deps:  # Ignorer les groupes vides ou à un seul élément sans deps externes
                ext_name = f"ext_group_{i+1}"
                ext_packages[ext_name] = {
                    'modules': modules,
                    'external_deps': list(ext_deps)
                }
                print(f"\n3. Groupe de dépendances externes {i+1}:")
                print(f"  Dépendances: {', '.join(sorted(ext_deps))}")
                print("  Modules:")
                for module in sorted(modules):
                    print(f"  - {module}")
        
        # Convertir le résultat en une structure cohérente
        proposed_structure = {
            'base_packages': base_packages,
            'cycle_packages': cycle_packages,
            'external_dependency_groups': ext_packages
        }
        
        return proposed_structure
    
    def visualize_dependencies(self, output_file='dependency_graph.png'):
        """Visualise le graphe de dépendances."""
        print(f"\nGénération du graphe de dépendances dans {output_file}...")
        
        plt.figure(figsize=(12, 10))
        pos = nx.spring_layout(self.dependency_graph, k=0.15, iterations=20)
        
        # Dessiner les nœuds avec des couleurs différentes selon le type
        standalone = [n for n in self.dependency_graph.nodes() if n in self.module_groups['standalone']]
        cycles = [n for scc in self.module_groups['cycles'] for n in scc if len(scc) > 1]
        
        nx.draw_networkx_nodes(self.dependency_graph, pos, nodelist=standalone, 
                              node_color='green', node_size=500, alpha=0.8)
        nx.draw_networkx_nodes(self.dependency_graph, pos, nodelist=cycles,
                              node_color='red', node_size=500, alpha=0.8)
        other_nodes = [n for n in self.dependency_graph.nodes() if n not in standalone and n not in cycles]
        nx.draw_networkx_nodes(self.dependency_graph, pos, nodelist=other_nodes,
                              node_color='blue', node_size=500, alpha=0.8)
        
        # Dessiner les arêtes et les étiquettes
        nx.draw_networkx_edges(self.dependency_graph, pos, arrows=True)
        
        # Simplifier les noms de modules pour l'affichage
        labels = {n: n.replace(f"{self.project_name}.", "") for n in self.dependency_graph.nodes()}
        nx.draw_networkx_labels(self.dependency_graph, pos, labels=labels, font_size=8)
        
        plt.title(f"Graphe de dépendances pour {self.project_name}")
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"Graphe enregistré dans {output_file}")
    
    def generate_restructuring_plan(self, output_dir='restructuring_plan'):
        """Génère un plan de restructuration."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # 1. Exporter la structure proposée en format JSON
        structure_file = output_path / 'proposed_structure.txt'
        with open(structure_file, 'w', encoding='utf-8') as f:
            proposed_structure = self.suggest_packages()
            
            f.write("# Plan de Restructuration pour " + self.project_name + "\n\n")
            
            f.write("## 1. Packages de Base (Sans dépendances internes)\n")
            for module in sorted(proposed_structure['base_packages']):
                f.write(f"- {module}\n")
            
            f.write("\n## 2. Packages avec Dépendances Circulaires\n")
            for cycle_name, modules in proposed_structure['cycle_packages'].items():
                f.write(f"\n### {cycle_name.replace('_', ' ').title()}\n")
                for module in sorted(modules):
                    f.write(f"- {module}\n")
            
            f.write("\n## 3. Groupes par Dépendances Externes\n")
            for group_name, group_info in proposed_structure['external_dependency_groups'].items():
                f.write(f"\n### {group_name.replace('_', ' ').title()}\n")
                f.write("Dépendances externes:\n")
                for dep in sorted(group_info['external_deps']):
                    f.write(f"- {dep}\n")
                f.write("\nModules:\n")
                for module in sorted(group_info['modules']):
                    f.write(f"- {module}\n")
        
        # 2. Exporter une matrice de dépendances
        matrix_file = output_path / 'dependency_matrix.txt'
        with open(matrix_file, 'w', encoding='utf-8') as f:
            f.write("# Matrice de Dépendances\n\n")
            
            # Créer une liste de tous les modules
            all_modules = sorted(self.dependencies.keys())
            
            # Écrire l'en-tête
            f.write("| Module | " + " | ".join(["Dép. " + str(i+1) for i in range(min(5, len(all_modules)))]) + " |\n")
            f.write("|" + "-"*10 + "|" + "".join(["-"*10 + "|" for _ in range(min(5, len(all_modules)))]) + "\n")
            
            # Écrire les dépendances
            for module in all_modules:
                internal_deps = sorted(self.dependencies[module]['internal'])
                deps_str = " | ".join([dep.replace(f"{self.project_name}.", "") if i < len(internal_deps) else "-" 
                                     for i in range(min(5, len(all_modules)))])
                f.write(f"| {module.replace(f'{self.project_name}.', '')} | {deps_str} |\n")

def main():
    """Point d'entrée principal pour l'analyseur de dépendances."""
    parser = argparse.ArgumentParser(
        description="Analyseur de dépendances pour restructurer des bibliothèques Python"
    )
    parser.add_argument(
        "project_path", 
        help="Chemin vers le répertoire racine du projet à analyser"
    )
    parser.add_argument(
        "project_name", 
        help="Nom du package Python (utilisé pour identifier les imports internes)"
    )
    parser.add_argument(
        "--output-dir", 
        default="output", 
        help="Répertoire de sortie pour les rapports générés"
    )
    parser.add_argument(
        "--graph", 
        action="store_true", 
        help="Générer une visualisation graphique des dépendances"
    )
    parser.add_argument(
        "--graph-format", 
        choices=["png", "pdf", "svg"], 
        default="png",
        help="Format du fichier graphique de sortie"
    )
    
    args = parser.parse_args()
    
    # Créer et exécuter l'analyseur
    analyzer = DependencyAnalyzer(args.project_path, args.project_name)
    
    # Exécuter l'analyse complète
    analyzer.find_python_files()
    analyzer.extract_imports()
    analyzer.analyze_dependency_structure()
    
    # Générer les résultats
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    
    # Générer le plan de restructuration
    analyzer.generate_restructuring_plan(output_dir=str(output_dir))
    
    # Générer le graphe si demandé
    if args.graph:
        graph_path = output_dir / f"dependency_graph.{args.graph_format}"
        analyzer.visualize_dependencies(output_file=str(graph_path))
    
    print(f"\nAnalyse terminée. Les résultats sont disponibles dans le répertoire {args.output_dir}")


if __name__ == "__main__":
    main()
