from fastapi.exceptions import RequestValidationError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
from application.available_service import AvailableService
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
    
    # Include controllers as routers
    app.include_router(ingestion_router)
    app.include_router(inference_router)

    # Configure logging with reduced verbosity
    logging.basicConfig(level=logging.ERROR, format="%(message)s")
    logger = logging.getLogger(__name__)

    @app.middleware("http")
    async def log_validation_errors(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            logger.error(str(exc))
            print(str(exc))
            return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def custom_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {str(exc)}")
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.error(f"Validation error: {exc.errors()}")
        return JSONResponse(status_code=422, content={"detail": exc.errors()})
    
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