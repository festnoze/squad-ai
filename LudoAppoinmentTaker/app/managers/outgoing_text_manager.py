import asyncio
import logging
import time
from app.managers.outgoing_manager import OutgoingManager

class OutgoingTextManager(OutgoingManager):
    
    def __init__(self, call_sid: str):
        super().__init__(call_sid)
        self.text_queue = asyncio.Queue()
        self.is_streaming = False
        self.stream_task = None
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"OutgoingTextManager initialized for call_sid: {call_sid}")

    async def queue_data(self, text_chunk: str):
        """
        Queues a text chunk to be sent.
        """
        if not self.is_streaming:
            self.logger.warning(f"OutgoingTextManager for call {self.call_sid} is not streaming. Ignoring text chunk: {text_chunk}")
            return
        await self.text_queue.put(text_chunk)
        self.logger.debug(f"Text chunk queued for call {self.call_sid}: {text_chunk[:50]}...")

    def _send_text_from_queue(self):
        """
        Continuously sends text from the queue over the WebSocket.
        """
        self.logger.info(f"Starting text sending loop for call {self.call_sid}")
        try:
            while True:
                if self.text_queue.empty():
                    time.sleep(0.1)
                    continue

                while self.is_streaming or not self.text_queue.empty():
                    try:
                        text_chunk = self.text_queue.get_nowait()
                        if text_chunk is None: # Sentinel value to stop
                            self.logger.info(f"Received None sentinel in text queue for call {self.call_sid}. Stopping.")
                            break
                        
                        print(text_chunk)
                        self.text_queue.task_done()
                    except asyncio.TimeoutError:
                        if not self.is_streaming and self.text_queue.empty():
                            self.logger.info(f"Text sending loop for call {self.call_sid} timed out and queue is empty, streaming stopped.")
                            break
                        continue
                    except Exception as e:
                        self.logger.error(f"Error sending text chunk for call {self.call_sid}: {e}", exc_info=True)
                        if not self.is_streaming:
                            break
                self.logger.info(f"Text sending loop for call {self.call_sid} finished.")
        except asyncio.CancelledError:
            self.logger.info(f"Text sending task cancelled for call {self.call_sid}.")
        finally:
            self.logger.info(f"Exiting _send_text_from_queue for call {self.call_sid}. Remaining items in queue: {self.text_queue.qsize()}")


    def run_background_streaming_worker(self) -> None:
        if self.audio_sender.is_sending or self.sender_task is not None:
            self.logger.error("Streaming is already running")
            return
            
        self.ask_to_stop_streaming_worker = False
        self.sender_task = asyncio.create_task(self._background_streaming_worker())
        self.logger.info("Audio streaming started")

    async def stop_background_streaming_worker_async(self) -> None:
        self.ask_to_stop_streaming_worker = True
        if self.sender_task:
            try:
                await asyncio.wait_for(self.sender_task, timeout=2.0)
            except asyncio.TimeoutError:
                self.logger.warning("Streaming worker did not stop in time, cancelling")
                self.sender_task.cancel()
            except Exception as e:
                self.logger.error(f"Error stopping streaming worker: {e}")
            finally:
                self.sender_task = None

    def _background_streaming_worker(self):
        while True:
            try:
                text_chunk = self.text_queue.get_nowait()
                if text_chunk is None: # Sentinel value to stop
                    self.logger.info(f"Received None sentinel in text queue for call {self.call_sid}. Stopping.")
                    break
                
                message_to_send = {"event": "text_response", "streamSid": self.call_sid, "text": text_chunk}
                self.websocket.send_json(message_to_send)
                self.logger.info(f"Sent text chunk for call {self.call_sid}: {text_chunk[:50]}...")
                self.text_queue.task_done()
            except asyncio.QueueEmpty:
                if self.ask_to_stop_streaming_worker:
                    self.logger.info(f"Text streaming stopped for call {self.call_sid}.")
                    break
                continue
            except Exception as e:
                self.logger.error(f"Error processing text chunk for call {self.call_sid}: {e}", exc_info=True)
                break

    def enqueue_text(self, text: str) -> bool:
        """
        Adds text to the queue for delivery.
        """
        return self.text_queue.put_nowait(text)

    def update_call_sid(self, call_sid: str) -> None:
        """
        Updates the call SID when it changes (e.g., when a new call starts or ends)
        Allows setting to None when resetting after a call ends
        """
        self.call_sid = call_sid

    async def cleanup(self):
        """
        Perform any cleanup operations.
        """
        self.logger.info(f"Cleaning up OutgoingTextManager for call {self.call_sid}.")
        await self.stop_streaming()
        self.logger.info(f"OutgoingTextManager cleanup finished for call {self.call_sid}.")
