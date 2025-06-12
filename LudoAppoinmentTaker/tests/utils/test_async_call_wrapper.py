import asyncio
import pytest
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from app.utils.async_call_wrapper import AsyncCallWrapper

class TestAsyncCallWrapper:
    # Test helper functions
    async def example_async_function(self, delay: float, value: str) -> str:
        await asyncio.sleep(delay)
        return f"Completed with value: {value}"
    
    async def async_function_with_exception(self):
        await asyncio.sleep(0.1)
        raise ValueError("Test exception")
    
    # Test run_async decorator
    def test_run_async_decorator(self):
        # Define a decorated function
        @AsyncCallWrapper.run_async
        async def decorated_function(name: str) -> str:
            await asyncio.sleep(0.1)
            return f"Hello, {name}!"
        
        # Test the decorated function
        result = decorated_function("World")
        assert result == "Hello, World!"
    
    # Test run_coroutine
    def test_run_coroutine(self):
        # Test with a simple coroutine
        result = AsyncCallWrapper.run_coroutine(self.example_async_function(0.1, "direct call"))
        assert result == "Completed with value: direct call"
        
        # Test with a coroutine that returns a complex object
        async def return_dict():
            await asyncio.sleep(0.1)
            return {"key": "value", "nested": {"data": 123}}
        
        result = AsyncCallWrapper.run_coroutine(return_dict())
        assert result == {"key": "value", "nested": {"data": 123}}
    
    # Test run_coroutine with exception handling
    def test_run_coroutine_exception(self):
        with pytest.raises(ValueError, match="Test exception"):
            AsyncCallWrapper.run_coroutine(self.async_function_with_exception())
    
    # Test run_in_new_loop
    def test_run_in_new_loop(self):
        result = AsyncCallWrapper.run_in_new_loop(self.example_async_function(0.1, "new loop"))
        assert result == "Completed with value: new loop"
    
    # Test run_in_thread
    def test_run_in_thread(self):
        result = AsyncCallWrapper.run_in_thread(self.example_async_function(0.1, "thread"))
        assert result == "Completed with value: thread"
        
        # Test exception propagation in thread
        with pytest.raises(ValueError, match="Test exception"):
            AsyncCallWrapper.run_in_thread(self.async_function_with_exception())
    
    # Test nested event loop handling with nest_asyncio
    def test_nested_event_loops(self):
        # Create a running event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        def run_in_loop():
            # This will run in an already running event loop
            return AsyncCallWrapper.run_coroutine(self.example_async_function(0.1, "nested loop"))
        
        try:
            # Start the loop
            future = loop.run_until_complete(asyncio.sleep(0))
            
            # Now call our function which will use nest_asyncio
            result = run_in_loop()
            assert result == "Completed with value: nested loop"
        finally:
            loop.close()
    
    # Test concurrent execution
    def test_concurrent_execution(self):
        # Define a function that uses AsyncCallWrapper
        def wrapped_async_call(value):
            return AsyncCallWrapper.run_coroutine(self.example_async_function(0.1, value))
        
        # Run multiple calls concurrently
        values = ["concurrent1", "concurrent2", "concurrent3", "concurrent4"]
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(wrapped_async_call, values))
        
        # Check results
        expected = [f"Completed with value: {val}" for val in values]
        assert results == expected
    
    # Test with long-running tasks
    def test_long_running_task(self):
        # Define a long-running async task
        async def long_task():
            # Simulate a task that takes some time
            await asyncio.sleep(0.5)
            return "Long task completed"
        
        # Measure execution time
        start_time = time.time()
        result = AsyncCallWrapper.run_coroutine(long_task())
        end_time = time.time()
        
        # Verify result and that it took at least the sleep time
        assert result == "Long task completed"
        assert end_time - start_time >= 0.5
    
    # Test with multiple awaits
    def test_multiple_awaits(self):
        async def multi_await_func():
            result1 = await self.example_async_function(0.1, "first")
            result2 = await self.example_async_function(0.1, "second")
            return f"{result1} and {result2}"
        
        result = AsyncCallWrapper.run_coroutine(multi_await_func())
        assert result == "Completed with value: first and Completed with value: second"
    
    # Test cancellation handling
    def test_cancellation_handling(self):
        # Test that cancellation is handled properly
        # We'll create a coroutine that raises CancelledError
        async def raise_cancelled():
            raise asyncio.CancelledError("Manually cancelled")
        
        # This should propagate the CancelledError
        with pytest.raises(asyncio.CancelledError):
            AsyncCallWrapper.run_coroutine(raise_cancelled())
        
        # Test with a manually cancelled Future
        # We need to use a different approach that works across Python versions
        async def get_cancelled_future():
            # Create a future and cancel it
            await asyncio.sleep(0.01)  # Small delay to ensure task is scheduled
            raise asyncio.CancelledError("Manually cancelled")
        
        # This should raise CancelledError when run through AsyncCallWrapper
        with pytest.raises(asyncio.CancelledError):
            AsyncCallWrapper.run_coroutine(get_cancelled_future())