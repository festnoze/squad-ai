import time
import functools
import inspect
import asyncio
from common_tools.helpers.txt_helper import txt

class MethodDecorator:
    @staticmethod
    def print_function_name_and_elapsed_time(display_param_value=None):
        """
        Decorator to display a method call, a param value (optional) and the execution time.
        
        :param param_to_display: The name of a parameter whose value should be displayed (optional).
        """
        def decorator(func):
            def before_invoke(args, kwargs):
                function_name = func.__name__
                param_value = None
                if display_param_value:
                    signature = inspect.signature(func)
                    bound_args = signature.bind(*args, **kwargs)
                    bound_args.apply_defaults()
                    param_value = bound_args.arguments.get(display_param_value, None)

                param_value_message = f"'{display_param_value}'= '{param_value}'" if param_value is not None else ""

                txt.print_with_spinner(f"> {function_name}({param_value_message}): Ongoing execution...")
                return function_name, param_value_message
            
            def after_invoke(function_name, param_value_message):
                txt.stop_spinner_replace_text(f"> {function_name}({param_value_message}): Execution done")
            
            def fails_upon_invoke(function_name, param_value_message):
                txt.stop_spinner_replace_text(f"Failure upon execution of: {function_name}({param_value_message})")
                
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                function_name, param_value_message = before_invoke(args, kwargs)                
                try:
                    result = func(*args, **kwargs)
                    after_invoke(function_name, param_value_message)        
                    return result  
                except Exception as e:
                    fails_upon_invoke(function_name, param_value_message)
                    raise e     

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                function_name, param_value_message = before_invoke(args, kwargs)
                try:
                    result = await func(*args, **kwargs)
                    after_invoke(function_name, param_value_message)
                    return result
                except Exception as e:
                    fails_upon_invoke(function_name, param_value_message)
                    raise e

            if inspect.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper

        return decorator
