from typeguard import typechecked
from functools import wraps
from types import FunctionType
from typing import Any, Callable, TypeVar

F = TypeVar('F', bound=Callable[..., Any])

def strong_type(func: F) -> F:
    """Decorator that enforces type checking at runtime.
    
    This is a wrapper around typeguard's @typechecked decorator.
    """
    if isinstance(func, FunctionType):
        @wraps(func)
        @typechecked
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)
        return wrapper
    raise TypeError("@strong_type must be used on a function")
