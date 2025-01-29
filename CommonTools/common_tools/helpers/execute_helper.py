import sys
import inspect
from types import FunctionType
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, AsyncGenerator, Generator, Callable
from functools import partial
from common_tools.helpers.txt_helper import txt

class Execute:

    # def async_wrapper_to_sync(async_function, *args, **kwargs):
    #     """A helper function to run async code in a synchronous context."""
    #     return asyncio.run(async_function(*args, **kwargs))
    
    # def async_generator_wrapper_to_sync(async_function: Callable[..., Any], *args: Any, **kwargs: Any) -> Generator:
    #     """Wrap an async generator to work as a sync generator."""
    #     async def async_gen():
    #         async for item in async_function(*args, **kwargs):
    #             yield item

    #     loop = asyncio.new_event_loop()
    #     asyncio.set_event_loop(loop)
    #     gen = async_gen()

    #     try:
    #         while True:
    #             yield loop.run_until_complete(gen.__anext__())
    #     except StopAsyncIteration:
    #         loop.close()

    @staticmethod
    def async_wrapper_to_sync(function_to_call: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """
        Encapsulate an asynchronous function execution into a synchronous function.
        Ensures compatibility with existing event loops - or creates a new one as needed.
        """
        try:
            # Attempt to get the current event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                if asyncio.iscoroutine(function_to_call):  
                    future = asyncio.ensure_future(function_to_call)
                elif asyncio.iscoroutinefunction(function_to_call):  
                    coroutine = function_to_call(*args, **kwargs)
                    future = asyncio.ensure_future(coroutine)
                else:
                    raise TypeError(f"Expected async function or coroutine object, got {type(function_to_call)}")

                return loop.run_until_complete(future)
            elif loop.is_closed():
                raise RuntimeError("Event loop is closed")
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(function_to_call(*args, **kwargs))
   
    # TODO: WARNING - It have issues with the event loop
    @staticmethod
    def async_generator_wrapper_to_sync(function_to_call: Callable[..., AsyncGenerator], *args: Any, **kwargs: Any) -> Generator:
        """
        Convert an asynchronous generator function to a synchronous generator.
        Use asyncio.Queue to bridge async results to the sync context.
        """
        async def put_results_in_queue(loop: asyncio.AbstractEventLoop):
            # Collect the results from the async generator and put them in the queue
            try:
                async for chunk in function_to_call(*args, **kwargs):
                    await queue.put(chunk)
                await queue.put(None)  # Indicate the end of the stream
            except Exception as e:
                await queue.put(e)  # Pass exceptions to the sync consumer

        # Create an event loop or use the existing one
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Create a queue to stream results from the async context to the sync context
        queue = asyncio.Queue()

        # Run the async producer in the same loop
        loop.create_task(put_results_in_queue(loop))

        # Consume results from the queue synchronously
        while True:
            item = loop.run_until_complete(queue.get())
            if item is None:  # End of the stream
                break
            if isinstance(item, Exception):  # Handle exceptions
                raise item
            yield item

    @staticmethod
    def run_sync_functions_in_parallel_threads(*functions_with_args):
        """
        Run the provided sync functions in parallel and return their results as a tuple.
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
    async def run_several_functions_as_concurrent_async_tasks(*functions_with_args, functions_with_streaming_indexes=None):
        """
        Run all kind of functions (synchronous, or asynchronous, or even with streaming) in parallel, as concurrent async tasks.
        
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
