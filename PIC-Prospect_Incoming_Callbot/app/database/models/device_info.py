import uuid
from datetime import datetime
from uuid import UUID


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

    def __init__(
        self,
        ip: str,
        user_agent: str,
        platform: str,
        app_version: str,
        os: str,
        browser: str,
        is_mobile: bool,
        id: UUID | None = None,
        created_at: datetime = None,
    ) -> None:
        self.ip = ip
        self.user_agent = user_agent
        self.platform = platform
        self.app_version = app_version
        self.os = os
        self.browser = browser
        self.is_mobile = is_mobile
        self.id = id if id is not None else uuid.uuid4()
        self.created_at = created_at

    def __repr__(self) -> str:
        return f"DeviceInfo: {self.ip} ({self.id})"

    def __str__(self) -> str:
        return self.__repr__()

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "ip": self.ip,
            "user_agent": self.user_agent,
            "platform": self.platform,
            "app_version": self.app_version,
            "os": self.os,
            "browser": self.browser,
            "is_mobile": self.is_mobile,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
