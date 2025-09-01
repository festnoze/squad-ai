from uuid import UUID

from pydantic import BaseModel


class DeviceInfoRequestModel(BaseModel):
    user_agent: str
    platform: str
    app_version: str
    os: str
    browser: str
    is_mobile: bool

    def to_dict(self):
        return {
            "user_agent": self.user_agent,
            "platform": self.platform,
            "app_version": self.app_version,
            "os": self.os,
            "browser": self.browser,
            "is_mobile": self.is_mobile,
        }


class UserRequestModel(BaseModel):
    user_id: UUID | None
    user_name: str
    IP: str  # TODO: should be moved to device_info in V2
    device_info: DeviceInfoRequestModel

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "IP": self.IP,
            "device_info": self.device_info.to_dict(),
        }
