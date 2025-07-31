
import os
import logging
import asyncio
from dotenv import load_dotenv
from starlette.responses import Response as StarletteResponse
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse, Response, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
#
from app import endpoints
from utils.envvar import EnvHelper
from phone_call_websocket_events_handler import PhoneCallWebsocketEventsHandlerFactory
from speech.pregenerated_audio import PreGeneratedAudio

class ApiConfig:
    # TMP TODO to remove: allow rapid transcription of a specified audio files
    # async def transcript_audio_async():
    #     from speech.speech_to_text import get_speech_to_text_provider
    #     filename = "C:/Users/e.millerioux/Music/" + "2025_07_30_19_12_25.wav"
    #     #audio_bytes = open(filename, "rb").read()
    #     stt = get_speech_to_text_provider()

    #     transcription = await stt.transcribe_audio_async(filename) # asyncio.create_task(tmp(audio_bytes[:1000000]))
                        
    #     #save into file
    #     with open("transcription2.txt", "w", encoding="utf-8") as f:
    #         f.write(transcription)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        #await ApiConfig.transcript_audio_async()

        # Startup logic
        logger = logging.getLogger(__name__)
        logger.info("Application startup.")
        
        # Pre-populate TTS cache with welcome texts
        try:
            await PreGeneratedAudio.populate_permanent_cache_at_startup_async()
            logger.info("TTS cache pre-population completed at startup.")
        except Exception as e:
            logger.error(f"Failed to pre-populate TTS cache at startup: {e}")
        
        if EnvHelper.get_test_audio():
            from testing.audio_test_simulator import AudioTestManager
            test_manager = AudioTestManager()
            # Lancer la simulation en arrière-plan
            asyncio.create_task(test_manager.run_if_enabled())

        try:
            yield
        finally:
            # Shutdown logic
            logger.info("Shutting down application.")
            if app:
                app.state.shutdown()

    # Configure the FastAPI app
    @staticmethod
    def create_app() -> FastAPI:
        app = FastAPI(
            title="Prospect Incoming Callbot API",
            description="Backend API for Voice Appointment Maker through Twilio",
            version= f"{datetime.now().strftime("%Y.%m.%d_%H.%M.%S")}",
            lifespan=ApiConfig.lifespan
        )
        app.state.shutdown = lambda: None
        
        load_dotenv()
        EnvHelper._init_load_env()
        
        app.include_router(endpoints.router)

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Configure loggings: one in *.log file, one in console
        logger = ApiConfig.configure_logging()

        # Initialize PhoneCallWebsocketEventsHandlerFactory
        endpoints.phone_call_websocket_events_handler_factory = PhoneCallWebsocketEventsHandlerFactory()
        
        logger.info('-----------------------------------------------------')
        logger.info('🌐 PIC (Prospect Incoming Callbot) API 🚀 started 🚀')
        logger.info('-----------------------------------------------------')


        def handle_error(request: Request, error_msg: str):
            logger.error(f"Logged Error: {error_msg}")

        # Middleware for centralized exception handling and response wrapping
        @app.middleware("http")
        async def controller_middleware(request: Request, call_next):
            try:
                # Perform the endpoint method call
                endpoint_output = await call_next(request)

                # Handle the endpoint output and build the HTTP response
                if isinstance(endpoint_output, (StreamingResponse, StarletteResponse)) or not hasattr(endpoint_output, "body_iterator"):
                    return endpoint_output

                if endpoint_output.body == b"" or endpoint_output.status_code == 204:
                    return JSONResponse(content={"status": "success"}, status_code=204)

                #TODO: log if request fails (don't works as this)
                # if endpoint_output.status_code > 299:
                #     logger.error(f"Call to endpoint {request.url} fails with status code {endpoint_output.status_code}")  
                
                response_body = b"".join([chunk async for chunk in endpoint_output.body_iterator])

                async def iterate_in_chunks(content: bytes):
                    yield content
                endpoint_output.body_iterator = iterate_in_chunks(response_body)  # Reset the body iterator

                return JSONResponse(
                    content={"status": "success", "data": response_body.decode("utf-8")},
                    status_code=endpoint_output.status_code,
                )

            except RequestValidationError as ve:
                handle_error(request, f"Validation error: {ve.errors()}")
                return JSONResponse(
                    status_code=422,
                    content={"status": "error", "detail": ve.errors()}
                )
            
            except Exception as exc:
                handle_error(request, f"Internal exception: {str(exc)}")
                return JSONResponse(
                    status_code=500,
                    content={"status": "error", "detail": str(exc)}
                )    

        @app.get("/ping")
        def ping() -> str:
            logger.error("Ping request received.")
            return "pong"

        @app.get("/logs/last", response_class=PlainTextResponse)
        def get_last_log_file() -> str:
            log_files = os.listdir("outputs/logs")
            log_files.sort()
            if not log_files or not any(log_files):
                return "<<<No log files found.>>>"
            latest_log_file = log_files[-1]
            with open(f"outputs/logs/{latest_log_file}", "r", encoding="utf-8") as file:
                return file.read()
                

        return app

    @staticmethod
    def configure_logging(app_name: str = "Prospect-Incoming-Callbot-API", logs_dir: str = "outputs/logs/"):
        if not os.path.isdir(logs_dir):
            os.makedirs(logs_dir)
        
        root_logger = logging.getLogger()
        if root_logger.hasHandlers():
            for handler in list(root_logger.handlers):
                root_logger.removeHandler(handler)
                handler.close()

        # Set root logger to a permissive level; handlers will filter.
        root_logger.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            "%(message)s | %(levelname)s [%(name)s ln.%(lineno)d] %(asctime)s",
            datefmt="%Y/%m/%d %H:%M:%S",
        )

        # Configure file handler to log to level: INFO
        file_handler = logging.FileHandler(
            f"{logs_dir}{app_name} {datetime.now().strftime('%Y-%m-%d %Hh%Mm%Ss')}.log",
            encoding="utf-8"
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        # Configure stream handler to use the level defined in environment settings
        stream_handler = logging.StreamHandler()        
        selected_log_level = logging.getLogger("uvicorn.error").level
        stream_handler.setLevel(selected_log_level)
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)

        logger = logging.getLogger(__name__)
        return logger