import time
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response as StarletteResponse
from contextlib import asynccontextmanager
from api.task_handler import task_handler

import os
import logging
from datetime import datetime

from webservices.all_controller import all_router
from common_tools.helpers.file_helper import file
from common_tools.helpers.txt_helper import txt

class ApiConfig:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            started_at = time.time()
            
            startup_duration = time.time() - started_at
            print(f"API Startup duration: {startup_duration:.2f}s.")
            yield

        finally:
            if app:
                await app.state.shutdown()

    # Configure the FastAPI app
    def create_app() -> FastAPI:
        app = FastAPI(
            title="RAG Chatbot API",
            description="Backend API for chatbot services RAG augmented",
            version= f"{datetime.now().strftime("%Y.%m.%d.%H%M%S")}",
            lifespan=ApiConfig.lifespan
        )
        app.state.shutdown = lambda: None
        
        # Include controllers as routers
        app.include_router(all_router)

        # All CORS settings are enabled for development purposes
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Configure logging with reduced verbosity
        # logging.basicConfig(level=logging.INFO, format="%(message)s")
        # logger = logging.getLogger(__name__)
        if not file.dir_exists("outputs/logs"):
            os.makedirs("outputs/logs")
            
        logging.basicConfig(
            level=logging.INFO,
            format="Log: %(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(f"outputs/logs/app.{datetime.now().strftime("%Y-%m-%d.%H%M%S")}.log"),
                logging.StreamHandler()  # Also print logs to the terminal
            ]
        )
        logger = logging.getLogger(__name__)
        txt.logger = logger
        
        def handle_error(request: Request, error_msg: str):
            if txt.waiting_spinner_thread:
                txt.stop_spinner_replace_text(f"Call to endpoint: '{request.url.components.path}' fails with error: {error_msg}")
            logger.error(f"Log Error: {error_msg}")

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
                handle_error(request, f"Unhandled exception: {str(exc)}")
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
            logger.error("Application startup: Task handler is running.")

        async def shutdown_event():
            """Handle application shutdown."""
            logger.error("Shutting down: Stopping the task handler.")
            task_handler.stop()
        
        app.add_event_handler("startup", startup_event)
        app.add_event_handler("shutdown", shutdown_event)

        return app