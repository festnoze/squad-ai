import uuid
import pytest

from utils.twilio_sid_converter import TwilioCallSidConverter

def test_bijection_roundtrip() -> None:
    u: uuid.UUID = uuid.uuid4()
    sid: str = TwilioCallSidConverter.uuid_to_call_sid(u)
    back: str = TwilioCallSidConverter.call_sid_to_uuid(sid)
    assert back == str(u)

def test_uuid_string_input() -> None:
    u: str = str(uuid.uuid4())
    sid: str = TwilioCallSidConverter.uuid_to_call_sid(u)
    assert sid.startswith("CA") and len(sid) == 34
    assert TwilioCallSidConverter.call_sid_to_uuid(sid) == u

def test_invalid_uuid_input() -> None:
    with pytest.raises(ValueError):
        TwilioCallSidConverter.uuid_to_call_sid("not-a-uuid")

def test_invalid_call_sid_prefix() -> None:
    with pytest.raises(ValueError):
        TwilioCallSidConverter.call_sid_to_uuid("SM" + "0"*32)

def test_invalid_call_sid_length() -> None:
    with pytest.raises(ValueError):
        TwilioCallSidConverter.call_sid_to_uuid("CA" + "0"*31)

def test_invalid_call_sid_chars() -> None:
    with pytest.raises(ValueError):
        TwilioCallSidConverter.call_sid_to_uuid("CA" + "g"*32)
