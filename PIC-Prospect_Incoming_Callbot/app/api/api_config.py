import logging
from starlette.responses import Response as StarletteResponse
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse, Response
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
    def create_app() -> FastAPI:
        app = FastAPI(
            title="Prospect Incoming Callbot API",
            description="Backend API for Voice Appointment Maker through Twilio",
            version= f"{datetime.now().strftime("%Y.%m.%d.%H%M%S")}",
            lifespan=ApiConfig.lifespan
        )
        app.state.shutdown = lambda: None
        
        from dotenv import load_dotenv
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

        # Configure logging: set level and clear existing handlers then create new ones.
        num_log_level = logging.getLogger("uvicorn.error").level
        root_logger = logging.getLogger()
        if root_logger.hasHandlers():
            for handler in list(root_logger.handlers):
                root_logger.removeHandler(handler)
                handler.close()

        # Set root logger to a permissive level; handlers will filter.
        root_logger.setLevel(logging.DEBUG)

        # Create a formatter
        formatter = logging.Formatter(
            "%(levelname)s (%(name)s ln.%(lineno)d) %(message)s"
        )

        # Configure file handler to log at INFO level
        file_handler = logging.FileHandler(
            f"outputs/logs/app.{datetime.now().strftime('%Y-%m-%d.%H%M%S')}.log"
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        # Configure stream handler to use the level from environment settings
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(num_log_level)
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)

        logger = logging.getLogger(__name__)


        # Initialize PhoneCallWebsocketEventsHandlerFactory
        endpoints.phone_call_websocket_events_handler_factory = PhoneCallWebsocketEventsHandlerFactory()
        
        logger.error('-----------------------------------------------------')
        logger.error('🌐 PIC (Prospect Incoming Callbot) API 🚀 started 🚀')
        logger.error('-----------------------------------------------------')

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
        async def ping() -> str:
            logger.error("Ping request received.")
            return "pong"
                
        async def startup_event():
            """Handle application startup."""
            logger.error("Application startup.")

        async def shutdown_event():
            """Handle application shutdown."""
            logger.error("Shutting down application.")
        
        app.add_event_handler("startup", startup_event)
        app.add_event_handler("shutdown", shutdown_event)

        return app