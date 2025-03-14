import os
import sys
import ast
import argparse
import networkx as nx
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any

class ImportVisitor(ast.NodeVisitor):
    def __init__(self):
        self.imports = set()
        self.from_imports = {}
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.add(alias.name)
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module is not None:
            module_path: str = node.module
            if node.level > 0:
                module_path = '.' * node.level + module_path
            for alias in node.names:
                if module_path in self.from_imports:
                    self.from_imports[module_path].add(alias.name)
                else:
                    self.from_imports[module_path] = {alias.name}

class DependencyAnalyzer:
    def __init__(self, project_path: str, project_name: str):
        self.project_path: Path = Path(project_path).resolve()
        self.project_name: str = project_name
        self.python_files: Dict[Path, str] = {}
        self.dependencies: Dict[str, Dict[str, Set[str]]] = {}
        self.dependency_graph: nx.DiGraph = nx.DiGraph()
        self.module_groups: Dict[str, Any] = {}
        self.module_to_group: Dict[str,int] = {}
        self.grouped_graph: nx.DiGraph = nx.DiGraph()
    def find_python_files(self) -> None:
        for root, _, files in os.walk(self.project_path):
            for file in files:
                if file.endswith('.py'):
                    file_path: Path = Path(root) / file
                    rel_path: Path = file_path.relative_to(self.project_path)
                    if file == '__init__.py':
                        module_path: str = str(rel_path.parent).replace(os.sep, '.')
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
    def extract_imports(self) -> None:
        for file_path, module_name in self.python_files.items():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    tree: ast.AST = ast.parse(f.read(), filename=str(file_path))
                visitor: ImportVisitor = ImportVisitor()
                visitor.visit(tree)
                internal_deps: Set[str] = set()
                external_deps: Set[str] = set()
                for imp in visitor.imports:
                    if imp == self.project_name or imp.startswith(f"{self.project_name}."):
                        internal_deps.add(imp)
                    else:
                        external_deps.add(imp)
                for module, names in visitor.from_imports.items():
                    if module == self.project_name or module.startswith(f"{self.project_name}."):
                        internal_deps.add(module)
                    else:
                        external_deps.add(module)
                self.dependencies[module_name] = {
                    'internal': internal_deps,
                    'external': external_deps
                }
                self.dependency_graph.add_node(module_name)
                for dep in internal_deps:
                    self.dependency_graph.add_edge(module_name, dep)
            except Exception:
                pass
    def analyze_dependency_structure(self) -> None:
        standalone_modules: List[str] = []
        for module, deps in self.dependencies.items():
            if not deps['internal']:
                standalone_modules.append(module)
        sccs = list(nx.strongly_connected_components(self.dependency_graph))
        external_dep_groups: Dict[frozenset, List[str]] = defaultdict(list)
        for module, deps in self.dependencies.items():
            ext_deps_key: frozenset = frozenset(deps['external'])
            external_dep_groups[ext_deps_key].append(module)
        self.module_groups = {
            'standalone': standalone_modules,
            'cycles': sccs,
            'by_external_deps': dict(external_dep_groups)
        }
    def partition_by_granularity(self, granularity: int) -> None:
        """
        Divise les modules en exactement 'granularity' sous-librairies si possible,
        en utilisant une combinaison de critères (dépendances internes, externes, hiérarchie).
        
        Args:
            granularity: Nombre cible de sous-librairies à créer
        """
        if granularity < 1:
            granularity = 1
        
        all_modules = list(self.dependency_graph.nodes())
        if len(all_modules) <= granularity:
            # Si le nombre de modules est inférieur ou égal à la granularité,
            # chaque module forme sa propre sous-librairie
            for idx, module in enumerate(all_modules, 1):
                self.module_to_group[module] = idx
        else:
            # Plusieurs stratégies pour créer les groupes
            strategies = [
                self._group_by_internal_deps,
                self._group_by_external_deps,
                self._group_by_hierarchy
            ]
            
            # Évaluer chaque stratégie et sélectionner celle qui donne le meilleur équilibre
            best_strategy = None
            best_score = float('inf')
            
            for strategy in strategies:
                groups, score = strategy(granularity)
                if score < best_score:
                    best_score = score
                    best_strategy = groups
            
            # Appliquer la meilleure stratégie
            idx = 1
            for group in best_strategy:
                for module in group:
                    self.module_to_group[module] = idx
                idx += 1
        
        # Créer le graphe des dépendances entre groupes
        self.grouped_graph = nx.DiGraph()
        for group_id in range(1, len(set(self.module_to_group.values())) + 1):
            self.grouped_graph.add_node(group_id)
        
        for source, target in self.dependency_graph.edges():
            g_s = self.module_to_group.get(source)
            g_t = self.module_to_group.get(target)
            if g_s and g_t and g_s != g_t:
                self.grouped_graph.add_edge(g_s, g_t)
    def _group_by_internal_deps(self, granularity: int) -> Tuple[List[List[str]], float]:
        """
        Groupe les modules selon leurs dépendances internes pour obtenir 'granularity' groupes.
        
        Args:
            granularity: Nombre cible de groupes
            
        Returns:
            Tuple contenant les groupes formés et un score d'évaluation (plus petit = meilleur)
        """
        undirected = self.dependency_graph.to_undirected()
        
        # Détecter des communautés initiales avec modularité
        initial_communities = list(nx.algorithms.community.greedy_modularity_communities(undirected))
        
        # Fusionner ou diviser jusqu'à obtenir granularity groupes
        if len(initial_communities) > granularity:
            # Fusionner les communautés les plus similaires
            while len(initial_communities) > granularity:
                # Calculer la similarité entre communautés (basée sur les connexions)
                similarity_scores = []
                for i in range(len(initial_communities)):
                    for j in range(i+1, len(initial_communities)):
                        comm1 = initial_communities[i]
                        comm2 = initial_communities[j]
                        edges_between = sum(1 for u in comm1 for v in comm2 if undirected.has_edge(u, v))
                        score = edges_between / (len(comm1) * len(comm2)) if len(comm1) * len(comm2) > 0 else 0
                        similarity_scores.append((score, i, j))
                
                # Fusionner les deux communautés les plus similaires
                if similarity_scores:
                    similarity_scores.sort(reverse=True)
                    _, i, j = similarity_scores[0]
                    new_community = initial_communities[i].union(initial_communities[j])
                    initial_communities = [comm for idx, comm in enumerate(initial_communities) if idx != i and idx != j]
                    initial_communities.append(new_community)
                else:
                    break
        
        elif len(initial_communities) < granularity:
            # Diviser les communautés les plus grandes
            while len(initial_communities) < granularity:
                # Trouver la plus grande communauté
                sizes = [len(comm) for comm in initial_communities]
                if max(sizes) <= 1:  # Ne peut plus diviser
                    break
                
                largest_idx = sizes.index(max(sizes))
                largest_comm = initial_communities[largest_idx]
                
                if len(largest_comm) > 1:
                    # Diviser en utilisant bisection
                    subgraph = self.dependency_graph.subgraph(largest_comm).to_undirected()
                    try:
                        left, right = nx.algorithms.community.kernighan_lin_bisection(subgraph)
                        initial_communities.pop(largest_idx)
                        initial_communities.append(set(left))
                        initial_communities.append(set(right))
                    except:
                        break
                else:
                    break
        
        # Évaluer l'équilibre des groupes
        avg_size = sum(len(comm) for comm in initial_communities) / len(initial_communities) if initial_communities else 0
        size_variance = sum((len(comm) - avg_size)**2 for comm in initial_communities) / len(initial_communities) if initial_communities else float('inf')
        
        return [list(comm) for comm in initial_communities], size_variance
    
    def _group_by_external_deps(self, granularity: int) -> Tuple[List[List[str]], float]:
        """
        Groupe les modules selon leurs dépendances externes communes.
        
        Args:
            granularity: Nombre cible de groupes
            
        Returns:
            Tuple contenant les groupes formés et un score d'évaluation (plus petit = meilleur)
        """
        # Créer des groupes initiaux basés sur les dépendances externes
        ext_dep_groups = defaultdict(list)
        for module, deps in self.dependencies.items():
            # Utiliser un ensemble figé (frozenset) des dépendances externes comme clé
            ext_deps_key = frozenset(deps['external'])
            ext_dep_groups[ext_deps_key].append(module)
        
        # Convertir en liste de groupes
        initial_groups = list(ext_dep_groups.values())
        
        # Ajuster le nombre de groupes pour atteindre granularity
        if len(initial_groups) > granularity:
            # Fusionner les groupes les plus similaires
            while len(initial_groups) > granularity:
                similarity_scores = []
                for i in range(len(initial_groups)):
                    for j in range(i+1, len(initial_groups)):
                        # Calculer similarité basée sur dépendances externes communes
                        group1_modules = set(initial_groups[i])
                        group2_modules = set(initial_groups[j])
                        
                        group1_ext_deps = set()
                        for module in group1_modules:
                            group1_ext_deps.update(self.dependencies[module]['external'])
                            
                        group2_ext_deps = set()
                        for module in group2_modules:
                            group2_ext_deps.update(self.dependencies[module]['external'])
                        
                        # Indice de Jaccard pour mesurer la similarité
                        if not group1_ext_deps and not group2_ext_deps:
                            similarity = 1.0  # Les deux n'ont pas de dépendances externes
                        else:
                            intersection = len(group1_ext_deps.intersection(group2_ext_deps))
                            union = len(group1_ext_deps.union(group2_ext_deps))
                            similarity = intersection / union if union > 0 else 0
                        
                        similarity_scores.append((similarity, i, j))
                
                if similarity_scores:
                    # Fusionner les deux groupes les plus similaires
                    similarity_scores.sort(reverse=True)
                    _, i, j = similarity_scores[0]
                    merged_group = initial_groups[i] + initial_groups[j]
                    initial_groups = [grp for idx, grp in enumerate(initial_groups) if idx != i and idx != j]
                    initial_groups.append(merged_group)
                else:
                    break
        
        elif len(initial_groups) < granularity:
            # Diviser les groupes les plus grands
            while len(initial_groups) < granularity:
                sizes = [len(grp) for grp in initial_groups]
                if max(sizes) <= 1:  # Ne peut plus diviser
                    break
                
                largest_idx = sizes.index(max(sizes))
                largest_group = initial_groups[largest_idx]
                
                if len(largest_group) > 1:
                    # Diviser en deux de manière équilibrée
                    mid = len(largest_group) // 2
                    initial_groups.pop(largest_idx)
                    initial_groups.append(largest_group[:mid])
                    initial_groups.append(largest_group[mid:])
                else:
                    break
        
        # Évaluer l'équilibre des dépendances externes
        ext_dep_per_group = []
        for group in initial_groups:
            group_ext_deps = set()
            for module in group:
                group_ext_deps.update(self.dependencies[module]['external'])
            ext_dep_per_group.append(len(group_ext_deps))
        
        avg_ext_deps = sum(ext_dep_per_group) / len(ext_dep_per_group) if ext_dep_per_group else 0
        ext_deps_variance = sum((deps - avg_ext_deps)**2 for deps in ext_dep_per_group) / len(ext_dep_per_group) if ext_dep_per_group else float('inf')
        
        # Également évaluer l'équilibre en taille
        sizes = [len(grp) for grp in initial_groups]
        avg_size = sum(sizes) / len(sizes) if sizes else 0
        size_variance = sum((size - avg_size)**2 for size in sizes) / len(sizes) if sizes else float('inf')
        
        # Score global (pondéré entre équilibre de taille et équilibre de dépendances)
        score = 0.5 * size_variance + 0.5 * ext_deps_variance
        
        return initial_groups, score
    
    def _group_by_hierarchy(self, granularity: int) -> Tuple[List[List[str]], float]:
        """
        Groupe les modules selon une hiérarchie: outils de base (peu de dépendances) 
        versus outils avancés (plus de dépendances).
        
        Args:
            granularity: Nombre cible de groupes
            
        Returns:
            Tuple contenant les groupes formés et un score d'évaluation (plus petit = meilleur)
        """
        all_modules = list(self.dependency_graph.nodes())
        
        # Calculer le "score de base" pour chaque module
        # (plus le score est faible, plus c'est un module de base)
        base_scores = {}
        for module in all_modules:
            # Un module de base a peu de dépendances internes entrantes mais potentiellement beaucoup sortantes
            in_degree = self.dependency_graph.in_degree(module)
            out_degree = self.dependency_graph.out_degree(module)
            
            # Score qui favorise les modules avec plus de dépendances sortantes que entrantes
            if in_degree == 0:
                base_scores[module] = -out_degree  # Les modules sans dépendances entrantes sont les plus "basiques"
            else:
                ratio = out_degree / in_degree if in_degree > 0 else out_degree
                base_scores[module] = -ratio  # Négatif car nous voulons trier par ordre croissant
        
        # Trier les modules par score (du plus basique au plus avancé)
        sorted_modules = sorted(all_modules, key=lambda m: base_scores[m])
        
        # Diviser en granularity groupes de taille égale
        groups = []
        target_size = len(sorted_modules) // granularity
        remainder = len(sorted_modules) % granularity
        
        start_idx = 0
        for i in range(granularity):
            # Distribuer le reste pour avoir des groupes plus équilibrés
            group_size = target_size + (1 if i < remainder else 0)
            if group_size > 0:  # S'assurer qu'on ne crée pas de groupes vides
                groups.append(sorted_modules[start_idx:start_idx + group_size])
                start_idx += group_size
            
            # Si on a utilisé tous les modules, sortir de la boucle
            if start_idx >= len(sorted_modules):
                break
        
        # Éliminer les groupes vides
        groups = [g for g in groups if g]
        
        # Évaluer l'équilibre des groupes
        sizes = [len(grp) for grp in groups]
        avg_size = sum(sizes) / len(sizes) if sizes else 0
        size_variance = sum((size - avg_size)**2 for size in sizes) / len(sizes) if sizes else float('inf')
        
        # Évaluer la cohérence hiérarchique des groupes (les modules de base ensemble, les avancés ensemble)
        hierarchy_variance = 0
        for group in groups:
            group_scores = [base_scores[module] for module in group]
            avg_score = sum(group_scores) / len(group_scores) if group_scores else 0
            hierarchy_variance += sum((score - avg_score)**2 for score in group_scores) / len(group_scores) if group_scores else 0
        hierarchy_variance /= len(groups) if groups else 1
        
        # Score global
        score = 0.7 * size_variance + 0.3 * hierarchy_variance
        
        return groups, score
    def suggest_packages(self) -> Dict[str, Any]:
        condensed_graph: nx.DiGraph = nx.condensation(self.dependency_graph)
        base_packages: List[str] = self.module_groups['standalone']
        cycle_packages: Dict[str, List[str]] = {}
        for i, cycle in enumerate(self.module_groups['cycles']):
            if len(cycle) > 1:
                cycle_name: str = f"cycle_{i+1}"
                cycle_packages[cycle_name] = list(cycle)
        ext_packages: Dict[str, Dict[str, Any]] = {}
        for i, (ext_deps, modules) in enumerate(self.module_groups['by_external_deps'].items()):
            if len(modules) > 1 and ext_deps:
                ext_name: str = f"ext_group_{i+1}"
                ext_packages[ext_name] = {
                    'modules': modules,
                    'external_deps': list(ext_deps)
                }
        proposed_structure: Dict[str, Any] = {
            'base_packages': base_packages,
            'cycle_packages': cycle_packages,
            'external_dependency_groups': ext_packages
        }
        return proposed_structure
    def visualize_sub_libraries(self, output_file: str = 'sub_libraries.png') -> None:
        plt.figure(figsize=(10, 8))
        pos = nx.spring_layout(self.grouped_graph, k=0.3)
        nx.draw_networkx_nodes(self.grouped_graph, pos, node_color='cyan', node_size=700)
        nx.draw_networkx_edges(self.grouped_graph, pos, arrows=True)
        labels = {n: f"Lib {n}" for n in self.grouped_graph.nodes()}
        nx.draw_networkx_labels(self.grouped_graph, pos, labels=labels, font_size=8)
        plt.title(f"Sous-librairies (granularite)")
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(output_file, dpi=300)
    def generate_restructuring_plan(self, output_dir='restructuring_plan') -> None:
        Path(output_dir).mkdir(exist_ok=True)
        structure_file: Path = Path(output_dir) / 'proposed_structure.txt'
        proposed_structure: Dict[str, Any] = self.suggest_packages()
        with open(structure_file, 'w', encoding='utf-8') as f:
            f.write("# Plan de Restructuration\n\n")
            f.write("## 1. Packages de Base\n")
            for module in sorted(proposed_structure['base_packages']):
                f.write(f"- {module}\n")
            f.write("\n## 2. Packages avec Dépendances Circulaires\n")
            for cycle_name, modules in proposed_structure['cycle_packages'].items():
                f.write(f"\n### {cycle_name}\n")
                for module in sorted(modules):
                    f.write(f"- {module}\n")
            f.write("\n## 3. Groupes par Dépendances Externes\n")
            for group_name, group_info in proposed_structure['external_dependency_groups'].items():
                f.write(f"\n### {group_name}\n")
                f.write("Dépendances externes:\n")
                for dep in sorted(group_info['external_deps']):
                    f.write(f"- {dep}\n")
                f.write("\nModules:\n")
                for module in sorted(group_info['modules']):
                    f.write(f"- {module}\n")
        matrix_file: Path = Path(output_dir) / 'dependency_matrix.txt'
        with open(matrix_file, 'w', encoding='utf-8') as f:
            f.write("# Matrice de Dépendances\n\n")
            all_modules: List[str] = sorted(self.dependencies.keys())
            f.write("| Module | D1 | D2 | D3 | D4 | D5 |\n")
            f.write("|-|-|-|-|-|-|\n")
            for module in all_modules:
                internal_deps: List[str] = sorted(self.dependencies[module]['internal'])
                deps_str: List[str] = [dep.replace(f"{self.project_name}.", "") for dep in internal_deps[:5]]
                while len(deps_str) < 5:
                    deps_str.append("-")
                f.write(f"| {module.replace(f'{self.project_name}.', '')} | {' | '.join(deps_str)} |\n")


def main():
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description="Analyseur de dépendances Python.")
    parser.add_argument("project_path", help="Chemin vers le répertoire racine du projet")
    parser.add_argument("project_name", help="Nom du package (pour identifier les imports internes)")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--graph", action="store_true")
    parser.add_argument("--graph-format", choices=["png", "pdf", "svg"], default="png")
    parser.add_argument("--granularity", type=int, default=10)
    args: argparse.Namespace = parser.parse_args()
    analyzer: DependencyAnalyzer = DependencyAnalyzer(args.project_path, args.project_name)
    analyzer.find_python_files()
    analyzer.extract_imports()
    analyzer.analyze_dependency_structure()
    analyzer.partition_by_granularity(args.granularity)
    analyzer.generate_restructuring_plan(output_dir=args.output_dir)
    if args.graph:
        graph_path: Path = Path(args.output_dir) / f"dependency_graph.{args.graph_format}"
        analyzer.visualize_sub_libraries(output_file=str(graph_path))

# if __name__ == "__main__":
#     main()
