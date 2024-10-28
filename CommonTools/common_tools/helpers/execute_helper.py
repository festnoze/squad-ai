import sys
import inspect
from types import FunctionType
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, AsyncGenerator, Generator, Callable
from functools import partial
from common_tools.helpers.txt_helper import txt

class Execute:
    @staticmethod
    def run_parallel(*functions_with_args):
        """
        Run the provided functions in parallel and return their results as a tuple.
        Supports function calls in multiple formats:
        - `task_a` : A function with no arguments
        - `(task_b, ("John",))` : Function with positional arguments
        - `(task_c, (2, 3), {'c': 5})` : Function with positional and keyword arguments
        :param functions_with_args: Functions with optional args/kwargs
        :return: Tuple of results in the same order as the provided functions
        """

        # Dynamically set max_workers based on the number of functions
        num_functions = len(functions_with_args)
        if num_functions == 0: 
            return ()
        
        results = [None] * num_functions
        
        # Use ThreadPoolExecutor to execute the functions in parallel
        with ThreadPoolExecutor(max_workers=num_functions) as executor:
            futures = []

            for index, item in enumerate(functions_with_args):
                # If the item is a function without arguments
                if callable(item):
                    futures.append((executor.submit(item), index))

                # If the item is a tuple with a function and its arguments
                elif isinstance(item, tuple):
                    func = item[0]
                    args = item[1] if len(item) > 1 else ()
                    kwargs = item[2] if len(item) > 2 else {}

                    # Ensure args is a tuple, even if it's a single non-iterable object (e.g., QuestionAnalysis)
                    if not isinstance(args, tuple):
                        args = (args,)

                    # Check if args contain non-iterable objects and wrap them in a tuple
                    if not isinstance(args, (tuple, list)):
                        args = (args,)

                    futures.append((executor.submit(func, *args, **kwargs), index))

                else:
                    raise ValueError(f"Invalid input: {item}")

            # Collect results based on the original order of submission
            for future, index in futures:
                results[index] = future.result()

        return tuple(results)

    @staticmethod
    async def run_parallel_async(*functions_with_args, functions_with_streaming_indexes=None):
        """
        Run synchronous and asynchronous functions in parallel, yielding results as they complete.
        
        :param functions_with_args: A mix of functions, both synchronous and asynchronous.
        :param functions_with_streaming_indexes: A list specifying the indices of functions that should be streamed.
                            If a function's index is included in this list, it will be treated as a streaming async function.
                            Example: [1] means the second function should be streamed.
        :yield: Yields results as they are completed.
        """
        if functions_with_streaming_indexes is None:
            functions_with_streaming_indexes = []

        # Separate tasks into sync, async, and streaming async
        async_tasks = []
        sync_tasks = []
        streaming_tasks = []

        # Classify the tasks and prepare them for execution
        for idx, item in enumerate(functions_with_args):
            if callable(item):  # Function without arguments
                if asyncio.iscoroutinefunction(item):
                    if idx in functions_with_streaming_indexes:
                        streaming_tasks.append((item, idx))
                    else:
                        async_tasks.append((item(), idx))
                else:
                    sync_tasks.append((item, (), {}, idx))
            elif isinstance(item, tuple):
                func = item[0]
                args = item[1] if len(item) > 1 else ()
                kwargs = item[2] if len(item) > 2 else {}

                # Ensure args is a tuple, even if it's a single non-iterable object
                if not isinstance(args, tuple):
                    args = (args,)

                if asyncio.iscoroutinefunction(func):
                    if idx in functions_with_streaming_indexes:
                        streaming_tasks.append((func, args, kwargs, idx))
                    else:
                        async_tasks.append((func(*args, **kwargs), idx))
                else:
                    sync_tasks.append((func, args, kwargs, idx))
            else:
                raise ValueError(f"Invalid input: {item}")
        
        # Handle sync tasks with ThreadPoolExecutor
        loop = asyncio.get_event_loop()
        results = [None] * len(functions_with_args)
        with ThreadPoolExecutor(max_workers=len(sync_tasks)) as executor:
            # Submit synchronous tasks to the executor
            sync_futures = [
                (loop.run_in_executor(executor, partial(func, *args, **kwargs)), idx)
                for func, args, kwargs, idx in sync_tasks
            ]

            # Collect results as the synchronous tasks complete
            for future, idx in sync_futures:
                # Wait for each future to complete
                result = await future
                results[idx] = result
                yield (idx, result)

        # Handle non-streaming async tasks
        for coro, idx in async_tasks:
            results[idx] = await coro
            yield (idx, results[idx])

        # Handle streaming async tasks
        for func, args, kwargs, idx in streaming_tasks:
            async for item in func(*args, **kwargs):
                yield (idx, item)
    
    @staticmethod
    def activate_global_function_parameters_types_verification():
        sys.setprofile(Execute._activate_strong_typed_functions_parameters)
        #threading.setprofile(Execute._activate_strong_typed_functions_parameters)

    @staticmethod
    def deactivate_global_function_parameters_types_verification():
        sys.setprofile(None)
        #threading.setprofile(None)

    @staticmethod
    def _activate_strong_typed_functions_parameters(frame, event, arg):
        """todo: don't work for now, work further or use decorator instead"""
        # We are only interested in function calls, not returns or other events
        if event != "call":
            return

        # Get the function being called using the code object in the frame
        func = frame.f_globals.get(frame.f_code.co_name)
        if not func:
            txt.print(f"Function not found: '{frame.f_code.co_name}'")
            return
        
        txt.print(f"Get function: '{func.__name__}")
        # Check if the object is a function
        if not isinstance(func, FunctionType):
            return

        try:
            # Get the function signature using the inspect module
            signature = inspect.signature(func)
            txt.print(f"Get function signature: '{func.__name__}")

            # The arguments passed to the function are stored in frame.f_locals
            args = frame.f_locals
            txt.print(f"Get arguments passed to the function: '{func.__name__}")
            for name, param in signature.parameters.items():
                # Check if the current argument has been passed and if it has an expected type annotation
                if name in args:
                    expected_type = param.annotation
                    if expected_type is not inspect.Parameter.empty:
                        txt.print(f"Get not empty argument: '{name} passed to the function: '{func.__name__}")
                        value = args[name]
                        if not value:
                            txt.print(f"No value found for argument: '{name} passed to the function: '{func.__name__}")
                            continue
                        # Verify if the value's type matches the expected arg's type
                        if not isinstance(value, expected_type):
                            txt.print(f"Get value: '{value}' for argument: '{name} passed to the function: '{func.__name__}  which does't match the expected type: '{expected_type.__name__}")
                            raise TypeError(f"Argument '{name}' of function '{func.__name__}' must be of type {expected_type.__name__}, but got {type(value).__name__}")

        except ValueError as e:
            txt.print(e)
        except TypeError as e:
            txt.print(e)

    @staticmethod
    def get_sync_generator_from_async(function_to_call: Callable[..., AsyncGenerator], *args: Any, **kwargs: Any) -> Generator:
        """
        Convert an asynchronous streaming function to a synchronous streaming generator.
        Explaination: Use asyncio.Queue() to bridge the asynchronous and synchronous contexts. 
        The asynchronous task put result chunks into the queue, which are then consumed synchronously. 
        This approach ensures that chunks are yielded incrementally, maintaining streaming behavior while going synchronous.
        """
        async def collect_results():
            # Use an async generator to collect results and yield them one by one
            async for chunk in function_to_call(*args, **kwargs):
                yield chunk
        
        async def put_results_in_queue():
            # Collect the results and put them in the queue for synchronous consumption
            try:
                async for chunk in collect_results():
                    await queue.put(chunk)
                # Indicate that all results have been put in the queue
                await queue.put(None)
            except Exception as e:
                await queue.put(e)

        # Create an event loop if there isn't one already
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError
        except RuntimeError:
            # If there is no event loop or it is closed, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
                
        # Create a queue to stream results from the async context to the sync context
        queue = asyncio.Queue()
        loop.create_task(put_results_in_queue())
        while True:
            item = loop.run_until_complete(queue.get())
            if item is None:  # End of the stream
                break
            if isinstance(item, Exception):  # If there was an error
                raise item
            yield item

