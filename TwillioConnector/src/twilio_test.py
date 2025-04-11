import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from twilio_controller import twilio_router  # Replace with the actual module name

app = FastAPI()
app.include_router(twilio_router)
client = TestClient(app)

def test_twilio_incoming_voice_call():
    response = client.post("/")
    assert response.status_code == 200
    assert "<Say" in response.text
    assert "<Record" in response.text
    assert 'transcribeCallback="/question/recording/transcription"' in response.text

@pytest.mark.parametrize("transcription_text,should_hangup", [
    ("Bonjour, comment ça va ?", False),
    ("au revoir", True),
    ("Salut, à la prochaine", True),
])
def test_twilio_question_recording_transcription(transcription_text: str, should_hangup: bool):
    response = client.post(
        "/question/recording/transcription",
        data={"TranscriptionText": transcription_text}
    )
    assert response.status_code == 200
    assert "<Say" in response.text
    assert transcription_text in response.text
    if should_hangup:
        assert "<Hangup" in response.text
    else:
        assert "<Record" in response.text