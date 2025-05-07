from enforce.typing import enforced
from functools import wraps
from types import FunctionType
from typing import Any

def strong_type(func: Any) -> Any:
    if isinstance(func, FunctionType):
        @wraps(func)
        @enforced
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)
        return wrapper
    raise TypeError("@strong_type must be used on a function")
