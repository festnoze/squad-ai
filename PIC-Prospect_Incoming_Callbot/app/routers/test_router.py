from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from utils.endpoints_api_key_required_decorator import api_key_required

test_router = APIRouter(prefix="/test")

# Secured endpoint to run performance tests with multiple concurrent incoming calls, do this GET query:
# http://127.0.0.1:8344/test/parallel-incoming-calls?api_key=test-key-9535782!b%&calls_count=3
@test_router.get("/parallel-incoming-calls")
@api_key_required
async def test_parallel_incoming_calls(request: Request) -> HTMLResponse:
    import asyncio
    from testing.audio_test_simulator import AudioTestManager

    test_manager = AudioTestManager()
    concurrent_calls_count = request.query_params.get("calls_count", 5)
    # Lancer la simulation en arrière-plan
    asyncio.create_task(test_manager.run_fake_incoming_calls(int(concurrent_calls_count)))
    return HTMLResponse(content="Test started successfully")
