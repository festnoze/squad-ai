import asyncio
import logging
from app.managers.outgoing_manager import OutgoingManager
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class OutgoingTextManager(OutgoingManager):
    def __init__(self, websocket: WebSocket, call_sid: str):
        super().__init__(call_sid)
        self.websocket = websocket
        self.text_queue = asyncio.Queue()
        self.is_streaming = False
        self.stream_task = None
        logger.info(f"OutgoingTextManager initialized for call_sid: {call_sid}, websocket: {websocket}")

    async def queue_data(self, text_chunk: str):
        """
        Queues a text chunk to be sent.
        """
        if not self.is_streaming:
            logger.warning(f"OutgoingTextManager for call {self.call_sid} is not streaming. Ignoring text chunk: {text_chunk}")
            return
        await self.text_queue.put(text_chunk)
        logger.debug(f"Text chunk queued for call {self.call_sid}: {text_chunk[:50]}...")

    async def _send_text_from_queue(self):
        """
        Continuously sends text from the queue over the WebSocket.
        """
        logger.info(f"Starting text sending loop for call {self.call_sid}")
        try:
            while self.is_streaming or not self.text_queue.empty():
                try:
                    text_chunk = await asyncio.wait_for(self.text_queue.get(), timeout=0.1)
                    if text_chunk is None: # Sentinel value to stop
                        logger.info(f"Received None sentinel in text queue for call {self.call_sid}. Stopping.")
                        break
                    
                    message_to_send = {"event": "text_response", "streamSid": self.call_sid, "text": text_chunk}
                    await self.websocket.send_json(message_to_send)
                    logger.info(f"Sent text chunk for call {self.call_sid}: {text_chunk[:50]}...")
                    self.text_queue.task_done()
                except asyncio.TimeoutError:
                    if not self.is_streaming and self.text_queue.empty():
                        logger.info(f"Text sending loop for call {self.call_sid} timed out and queue is empty, streaming stopped.")
                        break
                    continue
                except Exception as e:
                    logger.error(f"Error sending text chunk for call {self.call_sid}: {e}", exc_info=True)
                    if not self.is_streaming:
                        break
            logger.info(f"Text sending loop for call {self.call_sid} finished.")
        except asyncio.CancelledError:
            logger.info(f"Text sending task cancelled for call {self.call_sid}.")
        finally:
            logger.info(f"Exiting _send_text_from_queue for call {self.call_sid}. Remaining items in queue: {self.text_queue.qsize()}")

    def start_streaming(self):
        """
        Starts the text streaming process.
        """
        if self.is_streaming:
            logger.warning(f"Text streaming already started for call {self.call_sid}.")
            return
        logger.info(f"Starting text streaming for call {self.call_sid}.")
        self.is_streaming = True
        if self.stream_task is None or self.stream_task.done():
             self.stream_task = asyncio.create_task(self._send_text_from_queue())
             logger.info(f"Created text streaming task for call {self.call_sid}")
        else:
            logger.warning(f"Stream task for call {self.call_sid} already exists and is not done.")

    async def stop_streaming(self):
        """
        Stops the text streaming process.
        """
        logger.info(f"Attempting to stop text streaming for call {self.call_sid}.")
        if not self.is_streaming and (self.stream_task is None or self.stream_task.done()):
            logger.info(f"Text streaming already stopped or not started for call {self.call_sid}.")
            return

        self.is_streaming = False
        
        await self.text_queue.put(None)
        logger.info(f"Sent sentinel to text queue for call {self.call_sid}.")

        if self.stream_task and not self.stream_task.done():
            logger.info(f"Waiting for text streaming task to complete for call {self.call_sid}.")
            try:
                await asyncio.wait_for(self.stream_task, timeout=5.0)
                logger.info(f"Text streaming task for call {self.call_sid} completed.")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout waiting for text streaming task for call {self.call_sid} to complete. Cancelling.")
                self.stream_task.cancel()
                try:
                    await self.stream_task
                except asyncio.CancelledError:
                    logger.info(f"Text streaming task for call {self.call_sid} cancelled successfully.")
            except Exception as e:
                logger.error(f"Exception during text streaming task shutdown for call {self.call_sid}: {e}", exc_info=True)
        else:
            logger.info(f"No active text streaming task to stop for call {self.call_sid} or task already done.")
        
        while not self.text_queue.empty():
            try:
                self.text_queue.get_nowait()
                self.text_queue.task_done()
            except asyncio.QueueEmpty:
                break
            except Exception as e: 
                logger.warning(f"Error clearing text queue item during stop for call {self.call_sid}: {e}")
                break
        logger.info(f"Text streaming stopped and queue cleared for call {self.call_sid}. Queue size: {self.text_queue.qsize()}")

    async def cleanup(self):
        """
        Perform any cleanup operations.
        """
        logger.info(f"Cleaning up OutgoingTextManager for call {self.call_sid}.")
        await self.stop_streaming()
        logger.info(f"OutgoingTextManager cleanup finished for call {self.call_sid}.")
