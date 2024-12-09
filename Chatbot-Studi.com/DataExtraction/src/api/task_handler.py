import asyncio
import threading
from typing import Callable, Any

class AsyncTaskHandler:
    def __init__(self):
        """Initialize the task handler with a new event loop running in a separate thread."""
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.run_loop, daemon=True)
        self.thread.start()

    def run_loop(self):
        """Run the event loop forever in the separate thread."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def add_task(self, coro: Callable[..., Any], *args, **kwargs):
        """
        Schedule a coroutine to be executed in the separate event loop.

        Args:
            coro (Callable): The coroutine function to execute.
            *args: Positional arguments for the coroutine.
            **kwargs: Keyword arguments for the coroutine.
        """
        if not asyncio.iscoroutinefunction(coro):
            raise ValueError("The task function must be a coroutine.")
        asyncio.run_coroutine_threadsafe(coro(*args, **kwargs), self.loop)

    def stop(self):
        """Stop the event loop and wait for the thread to finish."""
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join()

# Initialize a singleton instance of the task handler
task_handler = AsyncTaskHandler()