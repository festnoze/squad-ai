import os
import ast
from collections import namedtuple
#
from common_tools.helpers.txt_helper import txt

class UselessCodeAnalyser:
    @staticmethod
    def perform_all_checks(target_folder_path: str, whitelist_array: list[str] = None, whitelist_filenames: list[str] = None):
        unused_files = UselessCodeAnalyser.detect_unused_files(target_folder_path, whitelist_array, whitelist_filenames)
        unused_functions = UselessCodeAnalyser.detect_unused_functions(target_folder_path, whitelist_array, whitelist_filenames)
        unused_imports = UselessCodeAnalyser.detect_unused_imports(target_folder_path, whitelist_array, whitelist_filenames)

        txt.print("Unused Files:")
        for file in unused_files:
            txt.print(f"  {file}")
        txt.print("\nUnused Functions/Methods:")
        for unused_function in unused_functions:
            if unused_function.class_name:
                txt.print(f"  {unused_function.file_path}:{unused_function.location[0]} - Method '{unused_function.class_name}.{unused_function.function_name}' is unused.")
            else:
                txt.print(f"  {unused_function.file_path}:{unused_function.location[0]} - Function '{unused_function.function_name}' is unused.")
        txt.print("\nUnused Imports:")
        for item in unused_imports:
            txt.print(f"  {item['file_path']}:{item['location'][0]} - Import '{item['name']}' is unused.")

    @staticmethod
    def detect_unused_files(target_folder_path: str, whitelist_array: list[str] = None, whitelist_filenames: list[str] = None):
        module_name_to_file_path, module_data = UselessCodeAnalyser.collect_modules_and_imports(target_folder_path, whitelist_array, whitelist_filenames)
        all_modules = set(module_name_to_file_path.keys())
        imported_modules = set()
        for data in module_data.values():
            imports = data.get('imports', set())
            for imported_module in imports:
                if imported_module in all_modules:
                    imported_modules.add(imported_module)
        unused_modules = all_modules - imported_modules
        unused_files = [module_name_to_file_path[module_name] for module_name in unused_modules]
        return unused_files

    @staticmethod
    def detect_unused_functions(target_folder_path: str, whitelist_array: list[str] = None, whitelist_filenames: list[str] = None):
        module_name_to_file_path, module_data = UselessCodeAnalyser.collect_modules_and_imports(target_folder_path, whitelist_array, whitelist_filenames)
        all_defined_functions = {}
        all_function_calls = set()

        for module_name, data in module_data.items():
            functions = data.get('functions', {})
            function_calls = data.get('function_calls', set())
            file_path = module_name_to_file_path[module_name]

            for (function_name, class_name), location in functions.items():
                all_defined_functions[(module_name, function_name, class_name)] = (file_path, location)

            all_function_calls.update(function_calls)

        # Find unused functions/methods
        UnusedFunction = namedtuple('UnusedFunction', ['file_path', 'function_name', 'class_name', 'location'])
        unused_functions = []
        for (module_name, function_name, class_name), (file_path, location) in all_defined_functions.items():
            if function_name not in all_function_calls:
                unused_functions.append(UnusedFunction(file_path, function_name, class_name, location))

        return unused_functions

    @staticmethod
    def detect_unused_imports(target_folder_path: str, whitelist_array: list[str] = None, whitelist_filenames: list[str] = None):
        module_name_to_file_path, module_data = UselessCodeAnalyser.collect_modules_and_imports(target_folder_path, whitelist_array, whitelist_filenames)
        unused_imports = []

        for module_name, data in module_data.items():
            imported_names = data.get('imported_names', set())
            used_names = data.get('used_names', set())
            unused_names = imported_names - used_names

            if unused_names:
                file_path = module_name_to_file_path[module_name]
                import_statements = data.get('import_statements', [])

                for import_stmt in import_statements:
                    name = import_stmt['name']
                    if name in unused_names:
                        location = import_stmt['location']
                        unused_imports.append({'file_path': file_path, 'name': name, 'location': location})

        return unused_imports

    @staticmethod
    def collect_modules_and_imports(target_folder_path: str, whitelist_array: list[str] = None, whitelist_filenames: list[str] = None):
        module_name_to_file_path = {}
        module_data = {}
        python_files = UselessCodeAnalyser.get_python_files(target_folder_path, whitelist_array, whitelist_filenames)

        for file_path in python_files:
            module_name = UselessCodeAnalyser.get_module_name(file_path, target_folder_path)
            module_name_to_file_path[module_name] = file_path
            parse_result = UselessCodeAnalyser.parse_file(file_path, module_name)
            if parse_result is None:
                continue
            module_data[module_name] = parse_result

        return module_name_to_file_path, module_data

    @staticmethod
    def get_python_files(target_folder_path: str, whitelist_array: list[str] = None, whitelist_filenames: list[str] = None):
        python_files = []
        for root, dirs, files in os.walk(target_folder_path):
            dirs[:] = [d for d in dirs if not UselessCodeAnalyser.is_whitelisted(os.path.join(root, d), whitelist_array, whitelist_filenames, target_folder_path)]
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    if not UselessCodeAnalyser.is_whitelisted(file_path, whitelist_array, whitelist_filenames, target_folder_path):
                        python_files.append(file_path)
        return python_files

    @staticmethod
    def is_whitelisted(path: str, whitelist_array: list[str], whitelist_filenames: list[str], target_folder_path: str):
        abs_path = os.path.abspath(path)
        
        if whitelist_array:
            for whitelist_path in whitelist_array:
                whitelist_path = os.path.abspath(whitelist_path)
                if os.path.commonpath([abs_path, whitelist_path]) == whitelist_path:
                    return True
        rel_path = os.path.relpath(path, start=target_folder_path)

        if whitelist_filenames and rel_path in whitelist_filenames:
            return True
        
        return False

    @staticmethod
    def get_module_name(file_path, target_folder_path):
        rel_path = os.path.relpath(file_path, target_folder_path)
        if rel_path.endswith('.py'):
            rel_path = rel_path[:-3]  # remove '.py' extension
        module_name = rel_path.replace(os.sep, '.')
        if module_name.endswith('.__init__'):
            module_name = module_name[:-9]  # remove '.__init__'
        return module_name

    @staticmethod
    def parse_file(file_path, current_module_name):
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
        try:
            tree = ast.parse(file_content)
        except SyntaxError as e:
            txt.print(f"Syntax error parsing {file_path}: {e}")
            return None

        UselessCodeAnalyser.set_parents(tree)

        importer = ImportCollector(current_module_name)
        importer.visit(tree)

        function_def_collector = FunctionDefCollector()
        function_def_collector.visit(tree)

        function_call_collector = FunctionCallCollector()
        function_call_collector.visit(tree)

        name_usage_collector = NameUsageCollector()
        name_usage_collector.visit(tree)

        return {
            'imports': importer.imports,
            'imported_names': importer.imported_names,
            'import_statements': importer.import_statements,
            'functions': function_def_collector.functions,
            'function_calls': function_call_collector.function_calls,
            'used_names': name_usage_collector.used_names,
        }

    @staticmethod
    def set_parents(node, parent=None):
        node.parent = parent
        for child in ast.iter_child_nodes(node):
            UselessCodeAnalyser.set_parents(child, node)

class ImportCollector(ast.NodeVisitor):
    def __init__(self, current_module_name):
        self.imports = set()  # modules imported
        self.imported_names = set()  # names imported
        self.import_statements = []
        self.current_module_name = current_module_name

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.add(alias.name)
            self.imported_names.add(alias.asname or alias.name.split('.')[0])
            location = (node.lineno, node.col_offset)
            self.import_statements.append({'name': alias.asname or alias.name.split('.')[0], 'location': location})

    def visit_ImportFrom(self, node):
        level = node.level
        module = node.module

        if level == 0:
            resolved_module = module or ''
        else:
            parts = self.current_module_name.split('.')
            if len(parts) >= level:
                base_module_parts = parts[:-level]
                if module:
                    base_module_parts.append(module)
                resolved_module = '.'.join(base_module_parts)
            else:
                resolved_module = module or ''

        self.imports.add(resolved_module)
        for alias in node.names:
            asname = alias.asname or alias.name
            self.imported_names.add(asname)
            location = (node.lineno, node.col_offset)
            self.import_statements.append({'name': asname, 'location': location})

class FunctionDefCollector(ast.NodeVisitor):
    def __init__(self):
        self.functions = {}

    def visit_FunctionDef(self, node):
        if isinstance(node.parent, ast.ClassDef):
            class_name = node.parent.name
        else:
            class_name = None
        function_name = node.name
        location = (node.lineno, node.col_offset)
        self.functions[(function_name, class_name)] = location
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        for child in node.body:
            child.parent = node
        self.generic_visit(node)

class FunctionCallCollector(ast.NodeVisitor):
    def __init__(self):
        self.function_calls = set()

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            # Function call
            function_name = node.func.id
            self.function_calls.add(function_name)
        elif isinstance(node.func, ast.Attribute):
            # Method call
            method_name = node.func.attr
            self.function_calls.add(method_name)
        self.generic_visit(node)

class NameUsageCollector(ast.NodeVisitor):
    def __init__(self):
        self.used_names = set()

    def visit_Name(self, node):
        self.used_names.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node):
        # Collect the attribute name
        self.used_names.add(node.attr)
        self.generic_visit(node)


# print("Analyse unused files/methods and imports of the current project:")
# unused_files_methods_imports = UselessCodeAnalyser.detect_unused_files(
#     ".", 
#     ['./common_tools/helpers', './common_tools/langchains', './common_tools/rag/rag_inference_pipeline', './common_tools/project'],
#     ['__init__.py', 'setup.py'])
# print(unused_files_methods_imports)