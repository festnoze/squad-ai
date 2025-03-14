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
        undirected = self.dependency_graph.to_undirected()
        communities = list(nx.algorithms.community.greedy_modularity_communities(undirected))
        final_groups: List[Set[str]] = []
        for c in communities:
            final_groups.extend(self.split_community(c, granularity))
        idx = 1
        for g in final_groups:
            for m in g:
                self.module_to_group[m] = idx
            idx += 1
        self.grouped_graph = nx.DiGraph()
        for group_id in range(1, idx):
            self.grouped_graph.add_node(group_id)
        for source, target in self.dependency_graph.edges():
            g_s = self.module_to_group.get(source)
            g_t = self.module_to_group.get(target)
            if g_s and g_t and g_s != g_t:
                self.grouped_graph.add_edge(g_s, g_t)
    def split_community(self, community: Set[str], granularity: int) -> List[Set[str]]:
        if len(community) <= granularity:
            return [community]
        subgraph = self.dependency_graph.subgraph(community).to_undirected()
        try:
            left, right = nx.algorithms.community.kernighan_lin_bisection(subgraph)
        except:
            return [community]
        return self.split_community(set(left), granularity) + self.split_community(set(right), granularity)
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
