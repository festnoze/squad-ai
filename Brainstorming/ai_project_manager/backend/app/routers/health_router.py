"""Health-check router. Exposes `GET /health` for smoke-testing."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def aget_health() -> dict[str, str]:
    """Return a minimal payload so uptime checks can verify the API is alive."""
    return {"status": "ok"}
