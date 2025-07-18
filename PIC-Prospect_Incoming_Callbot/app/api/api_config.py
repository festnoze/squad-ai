
import os
import logging
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

class ApiConfig:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
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
                
        async def startup_event():
            """Handle application startup."""
            logger.error("Application startup.")

        async def shutdown_event():
            """Handle application shutdown."""
            logger.error("Shutting down application.")
        
        app.add_event_handler("startup", startup_event)
        app.add_event_handler("shutdown", shutdown_event)

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