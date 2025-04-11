from fastapi import APIRouter, Request, Response, HTTPException
from twilio_service import TwilioService
from twilio.twiml.voice_response import VoiceResponse, Start, Transcription
from src.studi_public_website_client import StudiPublicWebsiteClient

handled_events_channel_and_ts: set = set()
twilio_service = TwilioService()
website_client :StudiPublicWebsiteClient = StudiPublicWebsiteClient("http://localhost:8281")

twilio_router = APIRouter(prefix="", tags=["Twilio"])

@twilio_router.post("/")
async def twilio_incoming_voice_call(request: Request) -> str:
    incoming_msg = """\
    Bonjour, et bienvenue chez Studi. 
    Nous sommes actuellement en dehors des heures d'ouverture. 
    Mais dites moi quelque chose, et je me ferait un plaisir de vous le répéter.
    Il vous suffit de dire 'au revoir' pour mettre fin à la conversation.
    """
    response: VoiceResponse = VoiceResponse()
    response.say(incoming_msg, voice="alice", language="fr-FR")
    start = Start()
    
    start.transcription(
        status_callback_url='/question/recording/transcription',
        name='Contact center transcription',
        languageCode='fr-FR')
    response.append(start)

    print(response)
    response.record(timeout=15, transcribe=True, transcribe_callback="/question/recording/transcription")
    return Response(content=str(response), media_type="application/xml")

@twilio_router.post("/question/recording/transcription")
async def twilio_question_recording_transcription(request: Request) -> str:
    form = await request.form()
    transcription_text: str = form.get("TranscriptionText", "")
    lower_text: str = transcription_text.lower()
    resp: VoiceResponse = VoiceResponse()
    resp.say("Vous avez dit: " + transcription_text, voice="alice", language="fr-FR")
    if "au revoir" in lower_text or "salut" in lower_text:
        resp.say("Merci d'avoir appelé. Au revoir, et à bientôt !", voice="alice", language="fr-FR")
        resp.hangup()
    else:
        resp.record(max_length=30, transcribe=True, transcribe_callback="/question/recording/transcription")
    return Response(content=str(resp), media_type="application/xml")

@twilio_router.get("/ping-api")
async def ping() -> str:
    return twilio_service.ping_external_api()
    