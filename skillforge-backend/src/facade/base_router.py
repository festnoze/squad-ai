from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

baserouter = APIRouter(prefix="", tags=["Base"])


@baserouter.get("/health", description="Check API health status and authentication details")
async def ahealth_check(request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={
            "authenticated": False,
            "instance_url": request.base_url._url,
            "sandbox": True,
            "auth_method": "JWT",
        },
    )


@baserouter.get("/ping", description="Allow to verify API availability")
def ping() -> str:
    return "pong"


@baserouter.get("/", description="Get API information and documentation links")
def root() -> JSONResponse:
    return JSONResponse(
        content={
            "service": "SkillForge API",
            "version": 1.0,
            "status": "running",
            "documentation": {"api_docs": "/docs", "redoc": "/redoc", "site_documentation": "/docs-site/"},
            "endpoints": {"health": "/ping"},
        }
    )
