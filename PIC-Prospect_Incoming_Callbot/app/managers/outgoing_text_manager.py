import asyncio
import logging

from managers.outgoing_manager import OutgoingManager


class OutgoingTextManager(OutgoingManager):
    def __init__(self, call_sid: str, outgoing_text_func=None, can_speech_be_interupted: bool = True):
        super().__init__(output_channel="text", can_speech_be_interupted=can_speech_be_interupted)
        self.call_sid = call_sid
        self.text_queue = asyncio.Queue()
        self.is_streaming = False
        self.stream_task = None
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"OutgoingTextManager initialized for call_sid: {call_sid}")
        self._outgoing_text_func = outgoing_text_func
        self.stream_sid = ""

    async def enqueue_text_async(self, text: str):
        """
        Queues a text to be sent.
        """
        if not self.is_streaming:
            self.logger.warning(f"OutgoingTextManager for call {self.call_sid} is not streaming. Ignoring text: {text}")
            return
        await self.text_queue.put(text)
        self.logger.debug(f"Text chunk queued for call {self.call_sid}: {text[:50]}...")

    def run_background_streaming_worker(self) -> None:
        if self.stream_task is not None:
            self.logger.error("Streaming is already running")
            return

        self.ask_to_stop_streaming_worker = False
        self.stream_task = asyncio.create_task(self._background_streaming_worker_async())
        self.logger.info("Text background streaming handler started")

    async def stop_background_streaming_worker_async(self) -> None:
        self.ask_to_stop_streaming_worker = True
        if self.stream_task:
            try:
                await asyncio.wait_for(self.stream_task, timeout=2.0)
            except TimeoutError:
                self.logger.warning("Streaming text worker did not stop in time, cancelling")
                self.stream_task.cancel()
            except Exception as e:
                self.logger.error(f"Error stopping streaming worker: {e}")
            finally:
                self.stream_task = None

    async def _background_streaming_worker_async(self) -> None:
        """
        Continuously sends text from the queue to stdout.
        """
        self.logger.info(f"Starting text sending loop for stream: {self.stream_sid}")
        try:
            while True:
                if self.text_queue.empty():
                    await asyncio.sleep(0.1)
                    continue

                while self.is_streaming or not self.text_queue.empty():
                    try:
                        text_chunk = self.text_queue.get_nowait()
                        if text_chunk is None:  # Sentinel value to stop
                            self.logger.info(
                                f"Received None sentinel in text queue for stream {self.stream_sid}. Stopping."
                            )
                            break

                        self.outgoing_text(text_chunk)

                        self.text_queue.task_done()
                    except TimeoutError:
                        if not self.is_streaming and self.text_queue.empty():
                            self.logger.info(
                                f"Text sending loop for stream {self.stream_sid} timed out and queue is empty, streaming stopped."
                            )
                            break
                        continue
                    except Exception as e:
                        self.logger.error(f"Error sending text chunk for stream {self.stream_sid}: {e}", exc_info=True)
                        if not self.is_streaming:
                            break
                self.logger.info(f"Text sending loop for stream {self.stream_sid} finished.")
        except asyncio.CancelledError:
            self.logger.info(f"Text sending task cancelled for stream {self.stream_sid}.")
        finally:
            self.logger.info(
                f"Exiting _send_text_from_queue for stream {self.stream_sid}. Remaining items in queue: {self.text_queue.qsize()}"
            )

    def outgoing_text(self, text: str) -> None:
        if self._outgoing_text_func:
            self._outgoing_text_func(text)
        else:
            print(text)

    async def enqueue_text_async(self, text: str) -> bool:
        """
        Adds text to the queue for delivery.
        """
        return self.text_queue.put_nowait(text)

    async def clear_text_queue(self) -> str:
        if self.can_speech_be_interupted:
            text = self.text_queue.get_nowait()
            await self.text_queue.put(None)
            self.logger.info("Text queue cleared for interruption")
            return text

    def has_text_to_be_sent(self) -> bool:
        """
        Returns True if there is still text to be sent.
        """
        return not self.text_queue.empty()

    def update_stream_sid(self, stream_sid: str) -> None:
        """
        Updates the stream SID when it changes (e.g., when a new call starts or ends)
        Allows setting to None when resetting after a call ends
        """
        self.stream_sid = stream_sid
        if not stream_sid:
            self.logger.info("Reset stream SID to None")
        else:
            self.logger.info(f"Updated stream SID to: {stream_sid}")
        return

    def is_sending(self) -> bool:
        """Returns True if an audio stream is currently outgoing."""
        return self.is_streaming

    async def cleanup(self):
        """
        Perform any cleanup operations.
        """
        self.logger.info(f"Cleaning up OutgoingTextManager for stream {self.stream_sid}.")
        await self.stop_streaming()
        self.logger.info(f"OutgoingTextManager cleanup finished for stream {self.stream_sid}.")
