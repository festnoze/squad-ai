# c:\Dev\squad-ai\LudoAppoinmentTaker\app\speech\outgoing_text_manager.py
import logging
import asyncio
from typing import Any, Optional
from fastapi import WebSocket # Assuming WebSocket is used for sending text

from app.speech.outgoing_manager import OutgoingManager

class OutgoingTextManager(OutgoingManager):
    """
    Manages outgoing text data streams, sending text directly to a client.
    """
    def __init__(self, websocket: Optional[WebSocket] = None): # WebSocket can be set later
        super().__init__()
        self.websocket = websocket
        self._text_queue = asyncio.Queue()
        self._processing_task: Optional[asyncio.Task] = None
        self.logger = logging.getLogger(__name__)
        self.logger.info("OutgoingTextManager initialized.")

    def set_websocket(self, websocket: WebSocket):
        """Sets or updates the WebSocket for sending text."""
        self.websocket = websocket
        self.logger.info(f"WebSocket set for OutgoingTextManager: {websocket}")

    async def queue_data(self, data: Any) -> None:
        """
        Queue text data for direct sending.

        Args:
            data: Text string to be sent.
        """
        if not self.is_active:
            self.logger.warning("Queue_data called but manager is not active. Ignoring.")
            return

        if not isinstance(data, str):
            self.logger.error(f"Invalid data type for text output: {type(data)}. Expected string.")
            return

        if data.strip(): # Ensure there's actual content
            self.logger.info(f"Queueing text for output: '{data[:50]}...'")
            await self._text_queue.put(data)
        else:
            self.logger.debug("Empty text received, not queueing for output.")

    async def _background_streaming_worker(self):
        """Worker task to process the queue and send text."""
        while self.is_active or not self._text_queue.empty():
            try:
                text_to_send = await asyncio.wait_for(self._text_queue.get(), timeout=1.0)
                self.logger.debug(f"Dequeued for sending: '{text_to_send}'")

                if self.websocket and self.websocket.client_state == self.websocket.client_state.CONNECTED:
                    try:
                        await self.websocket.send_text(text_to_send)
                    except Exception as e_ws:
                        self.logger.error(f"Error sending text via WebSocket: {e_ws}")
                        await self.stop_background_streaming_worker_async() # Stop manager if WebSocket fails critically
                        return
                else:
                    self.logger.warning("WebSocket not available or not connected, cannot send text.")
                    # Fallback or buffering could be implemented here
                    # For now, we just log. If critical, might stop.
                    # print(f"Output (No WebSocket): {text_to_send}") # Example fallback

                self._text_queue.task_done()

            except asyncio.TimeoutError:
                if not self.is_active and self._text_queue.empty():
                    break
                continue
            except Exception as e:
                self.logger.error(f"Error in send text worker: {e}", exc_info=True)
                if 'text_to_send' in locals() and not self._text_queue.empty():
                     self._text_queue.task_done()
                await asyncio.sleep(0.1)
        self.logger.info("Send text worker finished.")

    async def run_background_streaming_worker(self) -> None:
        await super().run_background_streaming_worker()
        if self._processing_task is None or self._processing_task.done():
            self._processing_task = asyncio.create_task(self._background_streaming_worker())
            self.logger.info("Send text worker task started.")
        else:
            self.logger.info("Send text worker task already running.")

    async def stop_background_streaming_worker_async(self) -> None:
        self.logger.info("Stopping OutgoingTextManager...")
        await super().stop_background_streaming_worker_async()

        if not self._text_queue.empty():
            self.logger.info("Waiting for text queue to empty...")
            await self._text_queue.join()

        if self.is_active and self._processing_task and not self._processing_task.done(): # Check is_active again
             self.logger.warning("Manager asked to stop, but worker is still running and queue might not be empty if stop was called abruptly.")


        if self._processing_task and not self._processing_task.done():
            self.logger.info("Waiting for send text worker task to finish...")
            try:
                await asyncio.wait_for(self._processing_task, timeout=5.0)
            except asyncio.TimeoutError:
                self.logger.warning("Timeout waiting for text worker to finish. Cancelling task.")
                self._processing_task.cancel()
            except Exception as e:
                self.logger.error(f"Exception while waiting for text worker: {e}")
        self.logger.info("OutgoingTextManager stopped.")