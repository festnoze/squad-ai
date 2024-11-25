from collections import namedtuple
from functools import wraps

def workflow_output(*names):
    def decorator(func):
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
