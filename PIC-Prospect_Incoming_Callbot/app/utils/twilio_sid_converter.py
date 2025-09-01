import re
import uuid


class TwilioCallSidConverter:
    @staticmethod
    def uuid_to_call_sid(uuid_value: str | uuid.UUID) -> str:
        if isinstance(uuid_value, uuid.UUID):
            hex_str: str = uuid_value.hex.lower()
        elif isinstance(uuid_value, str):
            hex_str: str = uuid.UUID(uuid_value).hex.lower()
        else:
            raise ValueError("uuid_value must be a str or uuid.UUID")
        return "CA" + hex_str

    @staticmethod
    def call_sid_to_uuid(call_sid: str) -> str:
        if not isinstance(call_sid, str):
            raise ValueError("call_sid must be a str")
        m: any = re.fullmatch(r"(CA)([0-9a-fA-F]{32})", call_sid)
        if not m:
            raise ValueError("Invalid Call SID format")
        h: str = m.group(2).lower()
        canonical: str = f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
        return str(uuid.UUID(canonical))
