import ast
import inspect
from typing import Any, Union, get_type_hints, get_origin

class StaticTypeAnalyzer(ast.NodeVisitor):
    def __init__(self, source: str):
        self.tree = ast.parse(source)
        self.errors: list[str] = []
        self.global_variable_types: dict[str, Any] = {}
        self.known_functions: dict[str, dict[str, Any]] = {}

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        annotations = {}
        try:
            exec(compile(ast.Module([node], []), filename="<ast>", mode="exec"), {}, annotations)
        except Exception:
            pass

        func = annotations.get(node.name, lambda: None)
        if not callable(func):
            return

        arg_types = get_type_hints(func)
        self.known_functions[node.name] = arg_types
        local_variable_types: dict[str, Any] = {}

        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Return) and stmt.value:
                inferred = self.infer_type(stmt.value, local_variable_types)
                expected = arg_types.get("return")
                if expected and not self.check_compatibility(inferred, expected):
                    self.errors.append(f"Line {stmt.lineno}: return type {inferred} incompatible with {expected}")

            elif isinstance(stmt, ast.Assign):
                if isinstance(stmt.value, ast.Call) and isinstance(stmt.value.func, ast.Name):
                    called_func = stmt.value.func.id
                    func_signature = self.known_functions.get(called_func)
                    return_type = func_signature.get("return") if func_signature else None
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            local_variable_types[target.id] = return_type
                            self.global_variable_types[target.id] = return_type
                else:
                    inferred = self.infer_type(stmt.value, local_variable_types)
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            local_variable_types[target.id] = inferred
                            self.global_variable_types[target.id] = inferred

            elif isinstance(stmt, ast.Call) and isinstance(stmt.func, ast.Name):
                func_name = stmt.func.id
                func_signature = self.known_functions.get(func_name)
                if func_signature:
                    for idx, arg in enumerate(stmt.args):
                        if idx < len(func_signature) - ("return" in func_signature):
                            param_name = list(k for k in func_signature if k != "return")[idx]
                            expected = func_signature[param_name]
                            inferred = self.infer_type(arg, local_variable_types)
                            if expected and not self.check_compatibility(inferred, expected):
                                self.errors.append(
                                    f"Line {stmt.lineno}: argument {idx + 1} for {func_name} incompatible: {inferred} vs {expected}"
                                )

        self.generic_visit(node)

    def infer_type(self, node: ast.AST, local_scope: dict[str, Any]) -> Union[type, str]:
        if isinstance(node, ast.Constant):
            return type(node.value)
        elif isinstance(node, ast.Name):
            return local_scope.get(node.id) or self.global_variable_types.get(node.id, node.id)
        elif isinstance(node, ast.BinOp):
            left = self.infer_type(node.left, local_scope)
            right = self.infer_type(node.right, local_scope)
            return left if left == right else "Unknown"
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            func_name = node.func.id
            signature = self.known_functions.get(func_name)
            if signature:
                return signature.get("return", "Unknown")
        return "Unknown"

    def check_compatibility(self, inferred: Any, expected: Any) -> bool:
        try:
            if isinstance(inferred, str):
                return True
            if isinstance(expected, type):
                return isinstance(inferred, expected) or issubclass(inferred, expected)
            origin = get_origin(expected)
            if origin:
                return isinstance(inferred, origin)
            return True
        except Exception:
            return False

    def report(self) -> list[str]:
        return self.errors

def run_static_analysis(obj: Any) -> None:
    source = inspect.getsource(obj)
    analyzer = StaticTypeAnalyzer(source)
    analyzer.visit(analyzer.tree)
    if analyzer.report():
        raise AssertionError("\n".join(analyzer.report()))
