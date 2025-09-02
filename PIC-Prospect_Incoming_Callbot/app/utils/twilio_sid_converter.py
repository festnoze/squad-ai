import re
import uuid
from uuid import UUID

class TwilioCallSidConverter:
    @staticmethod
    def uuid_to_call_sid(uuid_value: str | UUID) -> str:
        hex_str: str = ""
        if isinstance(uuid_value, uuid.UUID):
            hex_str = uuid_value.hex.lower()
        elif isinstance(uuid_value, str):
            hex_str = uuid.UUID(uuid_value).hex.lower()
        else:
            raise TypeError("wrong_uuid_value__type")
        return "CA" + hex_str

    @staticmethod
    def call_sid_to_uuid(call_sid: str) -> UUID:
        if not isinstance(call_sid, str):
            raise TypeError("wrong_call_sid__type")
        m = re.fullmatch(r"(CA)([0-9a-fA-F]{32})", call_sid)
        if not m:
            raise ValueError("Invalid_Call_SID_format")
        h: str = m.group(2).lower()
        return uuid.UUID(f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}")
