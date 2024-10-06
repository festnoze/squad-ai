from collections import namedtuple
from functools import wraps

def output_name(*names):
    """
    Decorator to assign names to the output values of a method.
    
    Args:
        *names: Variable length argument list specifying the names for output values.
        
    Returns:
        A decorator that wraps the function to return a namedtuple with the specified names.
    """
    def decorator(func):
        OutputTuple = namedtuple(f"{func.__name__}_output", names)
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            
            # Ensure the result is a tuple
            if not isinstance(result, tuple):
                result = (result,)
            
            if len(result) != len(names):
                raise ValueError(
                    f"Function '{func.__name__}' expected to return {len(names)} values, but got {len(result)}."
                )
            
            return OutputTuple(*result)
        
        return wrapper
    return decorator
