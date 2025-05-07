# Strong Types

> **Strong Types** is a library to import in your python projects to transform your python project as a strongly typed one! It performs a static and a runtime "type validation" on Python functions and classes, powered by `enforce` and a custom AST-based analyzer. It transforms type hints of all functions parameters and returned type into strongly typed ones. 

## Features

- You can simply add the: **@strong_type** decorator to any of your functions or classes for runtime validation to be performed (via `enforce`)
- **Static type analyzer** using Python’s AST to catch:
  - incorrect return types
  - wrong argument types
  - missing annotations
  - type mismatches across chained calls
  - cross-function and class-level propagation
  - union and container types (`list`, `dict`, `Union`...)
- Includes a complete **Tests suite** to cover dozens of detailed use cases
- **Pytest integration**

## Installation

```bash
pip install strong-types
```

## Usage

### Manual Runtime validation

```python
from strong_types.decorators import strong_type

@strong_type
def add(x: int, y: int) -> int:
    return x + y
```

### Static validation

```python
from strong_types.analyzer import run_static_analysis

def process(value: int) -> str:
    return str(value)

run_static_analysis(process)
```

### Pytest integration

```python
def test_static_consistency():
    from myapp.module import MyService
    run_static_analysis(MyService)
```

## License

MIT © Étienne Millerioux