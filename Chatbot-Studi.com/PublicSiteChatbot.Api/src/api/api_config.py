import os
import time
import logging
from datetime import datetime

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response as StarletteResponse
from contextlib import asynccontextmanager

from common_tools.helpers.txt_helper import txt

from facade.rag_ingestion_controller import ingestion_router
from facade.rag_inference_controller import inference_router
from application.available_service import AvailableService
from application.service_exceptions import QuotaOverloadException
from api.task_handler import task_handler

class ApiConfig:
    logger: logging.Logger = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            started_at = time.time()

            AvailableService.init(activate_print=True)  
            
            startup_duration = time.time() - started_at
            ApiConfig.logger.error(f"\n✓ API Startup duration: {startup_duration:.2f}s.")
            ApiConfig.logger.info("")
            ApiConfig.logger.error("  -------------------------------")
            ApiConfig.logger.error("  | 🌐  RAG API  🚀 started 🚀 |")
            ApiConfig.logger.error("  -------------------------------")

            yield

        finally:
            if app:
                await app.state.shutdown()

    # Configure the FastAPI app
    def create_app() -> FastAPI:
        # Configure loggings: one in *.log file, one in console        
        ApiConfig.logger = ApiConfig.configure_logging()
        txt.set_logger_as_stdout(ApiConfig.logger)

        app = FastAPI(
            title="RAG Chatbot API",
            description="Backend API for chatbot services RAG augmented",
            version= f"{datetime.now().strftime("%Y.%m.%d_%H.%M.%S")}",
            lifespan=ApiConfig.lifespan
        )
        async def noop_shutdown():
            pass
        app.state.shutdown = noop_shutdown
        
        # Include controllers as routers        
        app.include_router(ingestion_router)
        app.include_router(inference_router)
        
        # from facade.rag_evaluation_controller import evaluation_router
        # app.include_router(evaluation_router)

        # Must be limited to dev env. if reactivated
        # from facade.test_controller import test_router
        # app.include_router(test_router)
        
        # All CORS settings are enabled for development purposes
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        
        def handle_error(request: Request, error_msg: str):
            err_msg_txt = f"/!\\ ERROR: Call to endpoint: '{request.url.components.path}' fails with error: {error_msg}"
            
            if txt.waiting_spinner_thread:
                txt.stop_spinner_replace_text(err_msg_txt)
            else:
                ApiConfig.logger.error(err_msg_txt)

        # Middleware for centralized exception handling and response wrapping
        @app.middleware("http")
        async def controller_middleware(request: Request, call_next):
            try:
                ApiConfig.logger.info(f"ENDPOINT CALL> {request.url.components.path}")

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
            
            except QuotaOverloadException as qo:
                handle_error(request, f"Quota overload error: {str(qo)}")
                return JSONResponse(
                    status_code=429,
                    content={"status": "error", "detail": str(qo)}
                )
            
            except Exception as exc:
                handle_error(request, f"Unhandled exception: {str(exc)}")
                return JSONResponse(
                    status_code=500,
                    content={"status": "error", "detail": str(exc)}
                )    
                
        @app.get("/")
        def test_connect() -> str:
            ApiConfig.logger.info("Test connect request received.")
            return "Test API connection : success."

        @app.get("/ping")
        def ping() -> str:
            ApiConfig.logger.info("Ping request received.")
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
            ApiConfig.logger.info("Application startup: Task handler is running.")

        async def shutdown_event():
            """Handle application shutdown."""
            ApiConfig.logger.info("Shutting down: Stopping the task handler.")
            task_handler.stop()
        
        app.add_event_handler("startup", startup_event)
        app.add_event_handler("shutdown", shutdown_event)

        return app

    @staticmethod
    def configure_logging(app_name: str = "Studi.com-RAG-API", logs_dir: str = "outputs/logs/"):
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
            "%(message)s | %(levelname)s [ln.%(lineno)d] %(asctime)s",
            datefmt="%Y/%m/%d %H:%M:%S",
        )

        # Configure file handler to log at INFO level
        file_handler = logging.FileHandler(
            f"{logs_dir}{app_name} {datetime.now().strftime('%Y-%m-%d %Hh%Mm%Ss')}.log",
            encoding="utf-8"
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        # Configure stream handler to use the level from environment settings
        stream_handler = logging.StreamHandler()        
        selected_log_level = logging.getLogger("uvicorn.error").level
        stream_handler.setLevel(selected_log_level)
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)

        return logging.getLogger(__name__)