import os
from fastapi import FastAPI, Request, HTTPException
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv, find_dotenv

from src.studi_public_website_client import StudiPublicWebsiteClient

load_dotenv(find_dotenv())

SLACK_BOT_TOKEN: str = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET: str = os.environ["SLACK_SIGNING_SECRET"]
SLACK_BOT_USER_ID: str = os.environ["SLACK_BOT_USER_ID"]

app: FastAPI = FastAPI()
slack_client: WebClient = WebClient(token=SLACK_BOT_TOKEN)
signature_verifier: SignatureVerifier = SignatureVerifier(SLACK_SIGNING_SECRET)
handled_client_msg_ids: set = set()

website_client :StudiPublicWebsiteClient = StudiPublicWebsiteClient("http://localhost:8281")

@app.post("/slack/events")
async def slack_events(request: Request) -> dict:
    body_bytes: bytes = await request.body()
    body_str: str = body_bytes.decode("utf-8")
    if not signature_verifier.is_valid_request(body_str, request.headers):
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
            text: str = event.get("text", "")
            mention: str = f"<@{SLACK_BOT_USER_ID}>"
            text = text.replace(mention, "").strip()
            channel: str = event.get("channel")
            try:
                slack_client.chat_postMessage(channel=channel, text="Sure, I'll get right on that!")
                response_text: str = text.upper() #draft_email(text)
                slack_client.chat_postMessage(channel=channel, text=response_text)
                handled_client_msg_ids.add(client_msg_id)
            except SlackApiError as e:
                print(f"Error: {e}")
    return {"status": "ok"}


@app.get("/bot_user_id")
async def get_bot_user_id() -> dict:
    try:
        response: dict = slack_client.auth_test()
        return {"user_id": response["user_id"]}
    except SlackApiError as e:
        raise HTTPException(status_code=500, detail=f"Error: {e}")