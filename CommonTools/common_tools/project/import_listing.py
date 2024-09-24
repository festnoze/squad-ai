import os
import pkg_resources
from collections import defaultdict

class ImportListing:
    @staticmethod
    def find_imports(path):
        imports = defaultdict(list)
        
        for root, _, files in os.walk(path):
            for file in files:
                if file.endswith('.py') and not file == '__init__.py' and not file == 'setup.py': # Exclude package specific files
                    with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith('import ') or line.startswith('from '):
                                imports[file].append(line)
        
        return imports

    @staticmethod
    def get_used_packages(imports):
        used_packages = set()
        installed_packages = {pkg.key: pkg for pkg in pkg_resources.working_set}
        
        for file, lines in imports.items():
            for line in lines:
                parts = line.split()
                if parts[0] == 'import' or parts[0] == 'from':
                    package = parts[1].split('.')[0]
                else:
                    continue
                
                if package in installed_packages:
                    used_packages.add(package)
        
        return used_packages

    @staticmethod
    def discover_imports(project_path):
        imports = ImportListing.find_imports(project_path)
        return ImportListing.get_used_packages(imports)

# print("Packages used in this project:")
# used_packages = ImportListing.discover_imports(".")
# for pkg in sorted(used_packages):
#     print(pkg)
# pass
