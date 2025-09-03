import uuid
import pytest
from uuid import UUID
from utils.twilio_sid_converter import TwilioCallSidConverter

def test_bijection_roundtrip():
    original_uid: uuid.UUID = uuid.uuid4()
    sid: str = TwilioCallSidConverter.uuid_to_call_sid(original_uid)
    back: UUID = TwilioCallSidConverter.call_sid_to_uuid(sid)
    assert back == original_uid
    assert str(back) == str(original_uid)

def test_uuid_string_input():
    original_uid: UUID = uuid.uuid4()
    original_uid_str: str = str(original_uid)
    sid: str = TwilioCallSidConverter.uuid_to_call_sid(original_uid)
    sid_from_str: str = TwilioCallSidConverter.uuid_to_call_sid(original_uid_str)
    
    assert sid.startswith("CA") and len(sid) == 34
    assert TwilioCallSidConverter.call_sid_to_uuid(sid) == original_uid
    assert sid == sid_from_str
    assert original_uid_str == str(original_uid)

def test_invalid_uuid_input():
    with pytest.raises(ValueError):
        TwilioCallSidConverter.uuid_to_call_sid("not-a-uuid")

def test_invalid_call_sid_prefix():
    with pytest.raises(ValueError):
        TwilioCallSidConverter.call_sid_to_uuid("SM" + "0"*32)

def test_invalid_call_sid_length():
    with pytest.raises(ValueError):
        TwilioCallSidConverter.call_sid_to_uuid("CA" + "0"*31)

def test_invalid_call_sid_chars():
    with pytest.raises(ValueError):
        TwilioCallSidConverter.call_sid_to_uuid("CA" + "g"*32)
