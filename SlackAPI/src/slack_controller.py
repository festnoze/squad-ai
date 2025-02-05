from fastapi import FastAPI, Request, HTTPException
from slack_service import SlackService
from src.studi_public_website_client import StudiPublicWebsiteClient
from slack_sdk.errors import SlackApiError

app: FastAPI = FastAPI()
handled_client_msg_ids: set = set()
slack_service = SlackService()
website_client :StudiPublicWebsiteClient = StudiPublicWebsiteClient("http://localhost:8281")

@app.post("/slack/events")
async def slack_events(request: Request) -> dict:
    body_bytes: bytes = await request.body()
    body_str: str = body_bytes.decode("utf-8")
    if not slack_service.is_valid_request(body_str, request):
        raise HTTPException(status_code=403, detail="Invalid request signature")
    payload: dict = await request.json()
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}
    if payload.get("type") == "event_callback":
        event: dict = payload.get("event", {})
        if event.get("type") == "app_mention" or event.get("type") == "message":
            client_msg_id = event.get("client_msg_id", "")
            if not client_msg_id or client_msg_id in handled_client_msg_ids:
                return {"status": "ok"}
            user_query: str = event.get("text", "")
            mention: str = f"<@{slack_service.get_user_id()}>"
            user_query = user_query.replace(mention, "").strip()
            channel: str = event.get("channel")
            try:
                tmp_msg_id = slack_service.post_message(channel, "_Un instant ..._ Je réfléchis à votre question :hourglass_flowing_sand:", mrkdwn=True)
                msg_id = slack_service.post_response_to_query_from_external_api(channel, user_query)
                slack_service.delete_message(channel, tmp_msg_id)
                handled_client_msg_ids.add(client_msg_id)
                #handled_client_msg_ids.add(msg_id)
                
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