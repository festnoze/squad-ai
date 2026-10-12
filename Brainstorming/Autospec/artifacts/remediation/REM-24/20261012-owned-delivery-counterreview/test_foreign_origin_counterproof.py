"""Factory API Origin counterproof; only an inert callback is mutated."""
from types import SimpleNamespace

import httpx
import pytest

from autospec.api import server

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("origin", ["http://127.0.0.1:19533", "https://untrusted.example", "null"])
async def test_foreign_browser_origin_cannot_withdraw_factory_delivery(monkeypatch, origin):
    effects = []
    async def inert_withdraw():
        effects.append("unsafe mutation reached")
    monkeypatch.setattr(server, "pipelines", {
        "origin-meta": SimpleNamespace(aundeploy=inert_withdraw)
    })
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://127.0.0.1:8100"
    ) as client:
        response = await client.post("/api/projects/origin-meta/undeploy", headers={"Origin": origin})
    assert not effects, "CORS hid the response but executed a foreign-Origin mutation"
    assert response.status_code in {400, 403}, response.text
