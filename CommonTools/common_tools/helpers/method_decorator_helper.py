import time
import functools
import inspect
import asyncio
from typing import AsyncGenerator, Callable
from common_tools.helpers.txt_helper import txt
from common_tools.rag.rag_inference_pipeline.end_pipeline_exception import EndPipelineException

class MethodDecorator:
    @staticmethod
    def print_func_execution_infos(display_param_value=None):
        """
        Decorator to display a method call, a param value (optional), and the execution time,
        including handling async generators correctly.
        """
        def decorator(func: Callable):
            def before_invoke(args, kwargs):
                function_name = func.__name__
                param_value = None
                if display_param_value:
                    signature = inspect.signature(func)
                    bound_args = signature.bind(*args, **kwargs)
                    bound_args.apply_defaults()
                    param_value = bound_args.arguments.get(display_param_value, None)

                param_value_message = f"'{display_param_value}'= '{param_value}'" if param_value is not None else ""

                print(f"> {function_name}({param_value_message}) [Ongoing execution]")
                return function_name, param_value_message, time.time()

            def after_invoke(function_name, param_value_message, start_time):
                elapsed_time = time.time() - start_time
                print(f"> {function_name}({param_value_message}) [Execution done in {elapsed_time:.2f}s.]")

            def fails_upon_invoke(function_name, param_value_message, start_time):
                elapsed_time = time.time() - start_time
                print(f"{function_name}({param_value_message}) [Execution fails after {elapsed_time:.2f}s.]")

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                function_name, param_value_message, start_time = before_invoke(args, kwargs)
                try:
                    result = func(*args, **kwargs)
                    after_invoke(function_name, param_value_message, start_time)
                    return result                
                # Do not display pipeline ending exceptions, as they're not actual errors, but allow to exit the pipeline early
                except EndPipelineException as e: 
                    raise e
                except Exception as e:
                    fails_upon_invoke(function_name, param_value_message, start_time)
                    raise e

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                function_name, param_value_message, start_time = before_invoke(args, kwargs)
                try:
                    result = await func(*args, **kwargs)
                    after_invoke(function_name, param_value_message, start_time)
                    return result
                
                # Do not display pipeline ending exceptions, as they're not actual errors, but allow to exit the pipeline early
                except EndPipelineException as e: 
                    raise e
                except Exception as e:
                    fails_upon_invoke(function_name, param_value_message, start_time)
                    raise e

            @functools.wraps(func)
            async def async_generator_wrapper(*args, **kwargs) -> AsyncGenerator:
                function_name, param_value_message, start_time = before_invoke(args, kwargs)
                try:
                    async for item in func(*args, **kwargs):
                        yield item  # Stream the items from the generator
                    after_invoke(function_name, param_value_message, start_time)

                # Do not display pipeline ending exceptions, as they're not actual errors, but allow to exit the pipeline early
                except EndPipelineException as e: 
                    raise e
                except Exception as e:
                    fails_upon_invoke(function_name, param_value_message, start_time)
                    raise e

            if inspect.iscoroutinefunction(func):
                return async_wrapper
            elif inspect.isasyncgenfunction(func):
                return async_generator_wrapper
            else:
                return sync_wrapper

        return decorator