import os
import pkgutil
import importlib
import sys

def test_strong_types():
    # Import all modules in the app namespace
    project_namespace = "app"
    imported_modules = _import_all_modules_recursively(project_namespace)
    assert len(imported_modules) > 15
    
    # Verify modules are loaded in sys.modules
    project_modules = []
    all_modules = list(sys.modules.keys())
    for module_name in all_modules:
        if project_namespace and module_name.startswith(project_namespace):
            project_modules.append(module_name)
    assert len(project_modules) > 15
    
    # Run the type analyzer
    from strong_types.dynamic_type_analyzer import DynamicTypeAnalyzer
    DynamicTypeAnalyzer.initialize_strong_typing(project_namespace=project_namespace)

def test_dynamic_analyser(project_namespace: str = None, exclude_fastapi: bool = True) -> None:
    """Initialize strong typing for all modules of the project"""
    from strong_types.dynamic_type_analyzer import DynamicTypeAnalyzer
    for module_name in list(sys.modules.keys()):
        if project_namespace and module_name.startswith(project_namespace):
            module = sys.modules[module_name]
            DynamicTypeAnalyzer.apply_strong_type_to_module(
                module,
                exclude=lambda name: exclude_fastapi and ("fastapi" in module_name)
            )

def test_static_analyser():
    from app.api_config import ApiConfig
    from strong_types.static_type_analyzer import run_static_analysis
    run_static_analysis(ApiConfig)


def _import_all_modules_recursively(package_name):
    """Recursively import all modules in a package"""
    package = importlib.import_module(package_name)
    imported_modules = [package_name]
    
    # Check if it's a package with a __path__ attribute
    if hasattr(package, '__path__'):
        for _, name, is_pkg in pkgutil.iter_modules(package.__path__, package_name + '.'):
            imported_modules.append(name)
            module = importlib.import_module(name)
            if is_pkg:
                imported_modules.extend(_import_all_modules_recursively(name))
    
    return imported_modules