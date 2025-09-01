import logging
from functools import wraps

from fastapi import HTTPException
from fastapi.requests import Request
from utils.envvar import EnvHelper

logger: logging.Logger = logging.getLogger(__name__)


def api_key_required(func):
    """Decorator to require API key authorization for admin endpoints"""

    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        # Check API key authorization
        api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        if not api_key:
            raise HTTPException(
                status_code=401, detail="API key required. Provide via X-API-Key header or api_key query parameter"
            )

        if not EnvHelper.is_valid_admin_api_key(api_key):
            logger.warning(f"Invalid API key attempt: {api_key[:8]}...")
            raise HTTPException(status_code=403, detail="Invalid API key")

        # Remove api_key from query params if present
        if "api_key" in request.query_params:
            query_params_but_api_key = {k: v for k, v in request.query_params.items() if k != "api_key"}
            request._query_params = query_params_but_api_key

        logger.info(f"Authorized API access with key: {api_key[:8]}...")
        return await func(request, *args, **kwargs)

    return wrapper
