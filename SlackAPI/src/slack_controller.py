from fastapi import FastAPI, Request, HTTPException
from slack_service import SlackService
from src.studi_public_website_client import StudiPublicWebsiteClient
from slack_sdk.errors import SlackApiError

app: FastAPI = FastAPI()
handled_events_channel_and_ts: set = set()
slack_service = SlackService()
website_client :StudiPublicWebsiteClient = StudiPublicWebsiteClient("http://localhost:8281")

@app.post("/slack/events")
async def slack_events(request: Request) -> dict:
    body_bytes: bytes = await request.body()
    body_str: str = body_bytes.decode("utf-8")
    if not slack_service.is_valid_request(body_str, request):
        raise HTTPException(status_code=403, detail="Invalid request signature")
    payload: dict = await request.json()
    type = payload.get("type")
    if type == "url_verification":
        return {"challenge": payload.get("challenge")}
    if type == "event_callback":
        event: dict = payload.get("event", {})
        event_type = event.get("type") 
        if event_type == "app_mention" or event_type == "message":
            event_channel: str = event.get("channel")
            event_ts = event.get('ts')
            user_query: str = event.get("text", None)
            is_own_msg = event.get("subtype") or event.get("bot_id") or not user_query
            already_handled_event = (event_channel, event_ts) in handled_events_channel_and_ts
            
            if is_own_msg or already_handled_event:
                return {"status": "ok"}
            
            handled_events_channel_and_ts.add((event_channel, event_ts))
            
            mention: str = f"<@{slack_service.get_user_id()}>"
            user_query = user_query.replace(mention, "").strip()
            try:
                waiting_msg_id = slack_service.post_message(event_channel, "_Un instant ..._ Je réfléchis à votre question :hourglass_flowing_sand:", mrkdwn=True)
                msg_id = slack_service.post_streaming_response_to_query_from_external_api(event_channel, user_query, waiting_msg_id)
                #slack_service.delete_message(event_channel, waiting_msg_id)                
            except SlackApiError as e:
                print(f"Error: {e}")
    return {"status": "ok"}


@app.get("/bot_user_id")
async def get_bot_user_id() -> dict:
    try:
        user_id: dict = slack_service.get_user_id()
        return {"user_id": user_id}
    except SlackApiError as e:
        raise HTTPException(status_code=500, detail=f"Error: {e}")
    
@app.get("/ping")
async def ping() -> dict:
    return {"ping": "pong"}