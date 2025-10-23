import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Callable

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response as StarletteResponse

# from starlette.exceptions import HTTPException
from application.exceptions.quota_exceeded_exception import QuotaExceededException

#
from envvar import EnvHelper
from facade.base_router import baserouter
from facade.thread_router import thread_router
from facade.user_router import user_router
from facade.admin_router import admin_router
from facade.auth_router import auth_router


class ApiConfig:
    @staticmethod
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        # Startup logic
        logger = ApiConfig.configure_logging()
        logger.info("Application startup.")

        try:
            yield  # Application runs here
        finally:
            # Shutdown logic
            logger.info("Shutting down application.")
            if app:
                app.state.shutdown()

    # Configure the FastAPI app
    @staticmethod
    def create_app() -> FastAPI:
        app = FastAPI(
            title="SkillForge API",
            description="Backend API for SkillForge: one-to-one AI learning tutor",
            version=f"{datetime.now().strftime('%Y.%m.%d_%H.%M.%S')}",
            lifespan=ApiConfig.lifespan,
            swagger_ui_parameters={"persistAuthorization": True},
        )
        app.state.shutdown = lambda: None

        load_dotenv()
        EnvHelper.load_all_env_var()

        app.include_router(baserouter)
        app.include_router(auth_router)
        app.include_router(user_router)
        app.include_router(thread_router)
        app.include_router(admin_router)

        # Serve documentation as static files
        ApiConfig._setup_documentation_serving(app)

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
        # incoming_call_router.phone_call_websocket_events_handler_factory = PhoneCallWebsocketEventsHandlerFactory()

        logger.info("--------------------------------")
        logger.info("🌐 SkillForge API 🚀 started 🚀 ")
        logger.info("--------------------------------")

        def handle_error(request: Request, error_msg: str) -> None:
            logger.error(f"Logged Error: {error_msg}")

        # Middleware for centralized exception handling and response wrapping
        @app.middleware("http")
        async def controller_middleware(request: Request, call_next: Callable[[Request], Any]) -> Any:
            try:
                # Perform the endpoint method call
                endpoint_output = await call_next(request)

                # Handle the endpoint output and build the HTTP response
                if isinstance(endpoint_output, (StreamingResponse, StarletteResponse)) or not hasattr(endpoint_output, "body_iterator"):
                    return endpoint_output

                if endpoint_output.body == b"" or endpoint_output.status_code == 204:
                    return JSONResponse(content={"status": "success"}, status_code=204)

                response_body = b"".join([chunk async for chunk in endpoint_output.body_iterator])

                async def iterate_in_chunks(content: bytes) -> AsyncGenerator[bytes, None]:
                    yield content

                endpoint_output.body_iterator = iterate_in_chunks(response_body)  # Reset the body iterator

                return JSONResponse(
                    content={"status": "success", "data": response_body.decode("utf-8")},
                    status_code=endpoint_output.status_code,
                )

            except ValueError as e:
                handle_error(request, f"Value error: {e}")
                return JSONResponse(status_code=400, content={"status": "error", "detail": str(e)})

            except RequestValidationError as ve:
                handle_error(request, f"Validation error: {ve.errors()}")
                return JSONResponse(status_code=422, content={"status": "error", "detail": ve.errors()})

            except QuotaExceededException as e:
                handle_error(request, f"Quota exceeded error: {e}")
                return JSONResponse(status_code=429, content={"status": "error", "detail": str(e)})

            except Exception as exc:
                handle_error(request, f"Internal exception: {exc!s}")
                return JSONResponse(status_code=500, content={"status": "error", "detail": str(exc)})

        return app

    @staticmethod
    def _setup_documentation_serving(app: FastAPI) -> None:
        """Setup documentation serving for both development and production"""
        from pathlib import Path

        logger = ApiConfig.configure_logging()

        # Check if documentation serving is enabled
        if not EnvHelper.get_serve_documentation():
            logger.info("📚 Documentation serving disabled (SERVE_DOCUMENTATION=false)")
            return

        project_root = Path(__file__).parent.parent
        docs_site_path = project_root / "static" / "docs-site"

        # Check if built documentation exists
        if docs_site_path.exists() and docs_site_path.is_dir():
            logger.info(f"📚 Serving documentation at /docs-site/ from {docs_site_path}")
            app.mount("/docs-site", StaticFiles(directory=str(docs_site_path), html=True), name="docs-site")
        else:
            logger.warning(f"📚 Documentation not found at {docs_site_path}")
            logger.warning("   Run 'make docs-build' to build documentation")

            # Add a placeholder endpoint
            @app.get("/docs-site/")
            def docs_not_built() -> JSONResponse:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": "Documentation not built",
                        "message": "Run 'make docs-build' to build documentation",
                        "alternative": "For development, use 'make docs' to start mkdocs serve",
                    },
                )

    @staticmethod
    def configure_logging(app_name: str = "SkillForge-API", logs_dir: str = "outputs/logs/") -> logging.Logger:
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
        file_handler = logging.FileHandler(f"{logs_dir}{app_name} {datetime.now().strftime('%Y-%m-%d %Hh%Mm%Ss')}.log", encoding="utf-8")
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
