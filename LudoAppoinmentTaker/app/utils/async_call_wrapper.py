import asyncio
import threading
import nest_asyncio
from functools import wraps
from typing import TypeVar, Callable, Any, Coroutine, Optional, cast

T = TypeVar('T')

class AsyncCallWrapper:
    """
    A class that provides various methods to call async functions from synchronous code.
    This is the Python equivalent of C#'s GetAwaiter().GetResult() pattern.
    """
    
    @staticmethod
    def run_async(async_func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., T]:
        """
        Decorator to run an async function from a synchronous context.
        Uses the current event loop if one exists, or creates a new one.
        
        Example:
            @AsyncCallWrapper.run_async
            async def my_async_function():
                await asyncio.sleep(1)
                return "Done"
                
            # Now you can call it synchronously
            result = my_async_function()
        """
        @wraps(async_func)
        def wrapper(*args, **kwargs) -> T:
            return AsyncCallWrapper.run_coroutine(async_func(*args, **kwargs))
        return wrapper
    
    @staticmethod
    def run_coroutine(coroutine: Coroutine[Any, Any, T]) -> T:
        """
        Run a coroutine object from a synchronous context.
        This is the equivalent of C#'s GetAwaiter().GetResult()
        
        Args:
            coroutine: The coroutine to run
            
        Returns:
            The result of the coroutine
        """
        try:
            # Method 1: Try to get the running loop (Python 3.7+)
            try:
                loop = asyncio.get_running_loop()
                # If we're in a running event loop, use nest_asyncio to allow nested event loops
                nest_asyncio.apply()
                return loop.run_until_complete(coroutine)
            except RuntimeError:
                # No running event loop, create a new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(coroutine)
                finally:
                    asyncio.set_event_loop(None)
                    loop.close()
        except Exception as e:
            # Handle any other exceptions that might occur
            if isinstance(coroutine, asyncio.Task) and coroutine.cancelled():
                raise asyncio.CancelledError("Task was cancelled") from e
            raise
    
    @staticmethod
    def run_in_new_loop(coroutine: Coroutine[Any, Any, T]) -> T:
        """
        Run a coroutine in a completely new event loop.
        Useful when you want to isolate the execution from any existing event loop.
        """
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coroutine)
        finally:
            loop.close()
    
    @staticmethod
    def run_in_thread(coroutine: Coroutine[Any, Any, T]) -> T:
        """
        Run a coroutine in a separate thread with its own event loop.
        Useful when you want to avoid blocking the main thread.
        """
        result_container = []
        exception_container = []
        
        def thread_target():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result_container.append(loop.run_until_complete(coroutine))
            except Exception as e:
                exception_container.append(e)
            finally:
                loop.close()
        
        thread = threading.Thread(target=thread_target)
        thread.start()
        thread.join()
        
        if exception_container:
            raise exception_container[0]
        return result_container[0]

# Example usage
# if __name__ == "__main__":
#     async def example_async_function(delay: float, value: str) -> str:
#         await asyncio.sleep(delay)
#         return f"Completed with value: {value}"
    
#     # Method 1: Using the decorator
#     @AsyncCallWrapper.run_async
#     async def decorated_function(name: str) -> str:
#         await asyncio.sleep(1)
#         return f"Hello, {name}!"
    
#     # Method 2: Using run_coroutine directly
#     def call_async_directly():
#         return AsyncCallWrapper.run_coroutine(example_async_function(0.5, "direct call"))
    
#     # Method 3: Using run_in_new_loop
#     def call_in_new_loop():
#         return AsyncCallWrapper.run_in_new_loop(example_async_function(0.5, "new loop"))
    
#     # Method 4: Using run_in_thread
#     def call_in_thread():
#         return AsyncCallWrapper.run_in_thread(example_async_function(0.5, "thread"))
    
#     # Examples of calling these functions
#     print(decorated_function("World"))  # Calls async function with decorator
#     print(call_async_directly())        # Calls async function directly
#     print(call_in_new_loop())           # Calls async function in new loop
#     print(call_in_thread())             # Calls async function in separate thread
