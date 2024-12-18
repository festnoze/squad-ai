from fastapi.exceptions import RequestValidationError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse, Response
from starlette.responses import Response as StarletteResponse
from contextlib import asynccontextmanager
import logging
from application.available_service import AvailableService
from application.service_exceptions import QuotaOverloadException
from web_services.rag_ingestion_controller import ingestion_router
from web_services.rag_inference_controller import inference_router
from api.task_handler import task_handler
from common_tools.helpers.txt_helper import txt

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        AvailableService.init(activate_print=True)
        yield
    finally:
        if app:
            await app.state.shutdown()

# Configure the FastAPI app
def create_app() -> FastAPI:
    app = FastAPI(
        title="RAG API for Chatbot",
        description="API for RAG augmented chatbot backend services",
        version="1.0.0",
        lifespan=lifespan
    )
    app.state.shutdown = lambda: None
    
    # Include controllers as routers
    app.include_router(ingestion_router)
    app.include_router(inference_router)

    # Configure logging with reduced verbosity
    logging.basicConfig(level=logging.ERROR, format="%(message)s")
    logger = logging.getLogger(__name__)
    
    def handle_error(request: Request, error_msg: str):
        txt.stop_spinner_replace_text(f"Call to endpoint: '{request.url.components.path}' fails with error: {error_msg}")
        logger.error(f"Error: {error_msg}")

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
    
    async def startup_event():
        """Handle application startup."""
        logger.info("Application startup: Task handler is running.")

    async def shutdown_event():
        """Handle application shutdown."""
        logger.info("Shutting down: Stopping the task handler.")
        task_handler.stop()
    
    app.add_event_handler("startup", startup_event)
    app.add_event_handler("shutdown", shutdown_event)

    return app