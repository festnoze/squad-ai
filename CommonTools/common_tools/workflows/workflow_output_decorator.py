from collections import namedtuple
from functools import wraps
import inspect

#TODO: Handle namedtuple as output like this decorator allows 
def workflow_output(*names):
    def decorator(func):
        # Handle async functions 
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)
        else:
            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)

        # Set the attribute for the function to hold the output name(s)
        if len(names) == 1:
            wrapper._output_name = names[0]
        else:
            wrapper._output_name = list(names)

        return wrapper
    return decorator
