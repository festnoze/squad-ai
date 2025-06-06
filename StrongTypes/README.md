# Strong Types

*Python Library v.1.0.1*

##What is it for?

> **Strong Types** is a Python library capable to transforms your whole python project codebase into a **strongly typed** environment, like Java or C#. It combines 2 unique tools:
> 
> - **A static analyser**, based on an <u>AST analyzer</u>. This analysis is performed at "build" time (through your CI or a dedicated unit test). It ensures that all your type annotations are respected, before you even run your code.
> 
> - **A dynamic analyser**, based on [`enforce`](https://github.com/RussBaz/enforce)(which is comparable to Pydantic, but simpler and faster). This analysis is performed at runtime, it happens each time the code is actually executed. It ensures that every used objects instances has the awaited type, wherever there're used.

---

## Features

- **@strong_type decorator**: enforce strict typing at runtime for any function or class
- **Static analyzer**: validate typing rules across your codebase using the AST (Abstract Syntax Tree)
  - Incorrect return types
  - Wrong argument types
  - Missing annotations
  - Type mismatches across chained calls
  - Type propagation between functions and across classes
  - Validation of `Union`, `list`, `dict`, etc.
- **Test suite**: covers dozens of advanced and edge cases
- **Pytest integration**: run all checks automatically with your tests
- **Advanced propagation**: supports **type inference from other validated functions** and tracks cascading violations
- **Global verification**: validate entire modules/classes for structural type consistency
- **Automatic injection**: dynamically injects `@strong_type` in all your classes/functions automatically via `initialize_strong_typing`

---

## Installation

Install it from the web:

```bash
pip install strong-types
(when the library is available abroad)
```

---

Or install it from local library wheel, like so:

```textile
copy file: "strong_types-1.0.1-py3-none-any.whl to target project" dir.
add it to your project pip install "requirements.txt" file.
```

---

## Usage

### Manual runtime validation (per function or class)

```python
from strong_types.decorators import strong_type

@strong_type
def add(x: int, y: int) -> int:
    return x + y
```

You can also apply `@strong_type` to **entire classes**, and all methods will be validated:

```python
@strong_type
class Calculator:
    def square(self, x: int) -> int:
        return x * x
```

---

### Static validation

```python
from strong_types.analyzer import run_static_analysis

def process(value: int) -> str:
    return str(value)

run_static_analysis(process)  # passes
```

---

### Pytest integration (project-wide validation)

```python
def test_static_consistency():
    from mymodule import MyService
    run_static_analysis(MyService)
```

---

## ✅ Advanced Usage: Full Strong Typing for Your Project

### Auto-apply `@strong_type` everywhere with `initialize_strong_typing`

For large projects, you can automatically decorate all classes and functions by calling:

```python
from strong_types.dynamic_type_analyzer import DynamicTypeAnalyzer

DynamicTypeAnalyzer.initialize_strong_typing(project_namespace="myproject")
```

This will:

- Apply `@strong_type` to all classes in all modules starting with `"myproject"` (loaded in `sys.modules`)
- Skip external packages like `fastapi` by default

You can run this at the **entry point** of your application to enforce runtime typing globally.

Example (in `main.py`):

```python
if __name__ == "__main__":
    from strong_types.dynamic_type_analyzer import DynamicTypeAnalyzer
    DynamicTypeAnalyzer.initialize_strong_typing(project_namespace="myapp")
    app.run()
```

---

## License

MIT © Étienne Millerioux