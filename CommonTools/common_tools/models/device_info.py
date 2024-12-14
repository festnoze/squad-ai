from typing import Optional
from uuid import UUID
import uuid
from datetime import datetime

class DeviceInfo:
    id: UUID
    ip: str
    user_agent: str
    platform: str
    app_version: str
    os: str
    browser: str
    is_mobile: bool
    created_at: datetime

    def __init__(self, ip: str, user_agent: str, platform: str, app_version: str, os: str, browser: str, is_mobile: bool, id: Optional[UUID] = None, created_at: datetime = None) -> None:
        self.ip = ip
        self.user_agent = user_agent
        self.platform = platform
        self.app_version = app_version
        self.os = os
        self.browser = browser
        self.is_mobile = is_mobile
        self.id = id if id is not None else uuid.uuid4()
        self.created_at = created_at