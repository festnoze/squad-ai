import sys
import inspect
from typing import Any, Callable, Type
from strong_types.decorators import strong_type

class DynamicTypeAnalyzer:
    @staticmethod
    def apply_strong_type_to_class(cls: Type[Any], exclude: Callable[[str], bool] = lambda name: False) -> Type[Any]:
        """Apply strong_type to all methods of a class"""
        for name, method in inspect.getmembers(cls, inspect.isfunction):
            if not exclude(name):
                setattr(cls, name, strong_type(method))
        return cls

    @staticmethod
    def apply_strong_type_to_module(module: Any, exclude: Callable[[str], bool] = lambda name: False) -> None:
        """Apply strong_type to all classes of a module"""
        for name, obj in inspect.getmembers(module, inspect.isclass):
            DynamicTypeAnalyzer.apply_strong_type_to_class(obj, exclude=exclude)

    @staticmethod
    def initialize_strong_typing(project_namespace: str = None, exclude_fastapi: bool = True) -> None:
        """Initialize strong typing for all modules of the project"""
        for module_name in list(sys.modules.keys()):
            if project_namespace and module_name.startswith(project_namespace):
                module = sys.modules[module_name]
                DynamicTypeAnalyzer.apply_strong_type_to_module(
                    module,
                    exclude=lambda name: exclude_fastapi and ("fastapi" in module_name)
                )
