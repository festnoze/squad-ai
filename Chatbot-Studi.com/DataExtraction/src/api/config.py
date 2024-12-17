from fastapi.exceptions import RequestValidationError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
from application.available_service import AvailableService
from application.service_exceptions import QuotaOverloadException
from web_services.rag_ingestion_controller import ingestion_router
from web_services.rag_inference_controller import inference_router
from api.task_handler import task_handler

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        AvailableService.init(activate_print=True)
        yield
    finally:
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

    # Middleware for centralized exception handling and response wrapping
    @app.middleware("http")
    async def custom_middleware(request: Request, call_next):
        try:
            response = await call_next(request)

            # If response body is empty, return 204 success
            if response.body == b"" or response.status_code == 204:
                return JSONResponse(content={"status": "success"}, status_code=204)

            # Wrap successful responses
            content = await response.body()
            return JSONResponse(
                content={"status": "success", "data": content.decode("utf-8")},
                status_code=200
            )

        except RequestValidationError as ve:
            # Validation errors (specific handling)
            logger.error(f"Validation error: {ve.errors()}")
            return JSONResponse(
                status_code=422,
                content={"status": "error", "detail": ve.errors()}
            )
        
        except QuotaOverloadException as ve:
            # Validation errors (specific handling)
            logger.error(f"Validation error: {ve.errors()}")
            return JSONResponse(
                status_code=429,
                content={"status": "error", "detail": ve.errors()}
            )

        except Exception as exc:
            # General exception handling
            logger.error(f"Unhandled exception: {str(exc)}")
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