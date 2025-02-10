import asyncio
import threading
from typing import Callable, Any, Dict, List
from concurrent.futures import Future

class AsyncTaskHandler:
    def __init__(self):
        """Initialize the task handler with a new event loop running in a separate thread."""
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.run_loop, daemon=True)
        self.thread.start()
        self.task_registry: Dict[str, List[Future]] = {}  # Maps task_id to a list of Futures

    def run_loop(self):
        """Run the event loop forever in the separate thread."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def add_task(self, task_id: str, coro: Callable[..., Any], *args, **kwargs):
        """
        Schedule a coroutine to be executed in the separate event loop.

        Args:
            coro (Callable): The coroutine function to execute.
            task_id (str): An identifier for the task.
            *args: Positional arguments for the coroutine.
            **kwargs: Keyword arguments for the coroutine.
        """
        if not asyncio.iscoroutinefunction(coro):
            raise ValueError("The task function must be a coroutine.")
        future = asyncio.run_coroutine_threadsafe(coro(*args, **kwargs), self.loop)
        if task_id not in self.task_registry:
            self.task_registry[task_id] = []
        self.task_registry[task_id].append(future)

    def get_unfinished_tasks_ids(self) -> List[str]:
        unfinished_tasks_ids = []
        for task_id, futures in self.task_registry.items():
            for future in futures:
                if not future.done():
                    unfinished_tasks_ids.append(task_id)
        return unfinished_tasks_ids
    
    def is_task_ongoing(self, task_id: str) -> bool:
        return task_id in self.get_unfinished_tasks_ids()

    def stop(self):
        """Stop the event loop and wait for the thread to finish."""
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join()

# Initialize a singleton instance of the task handler
task_handler = AsyncTaskHandler()