from typing import Optional
from uuid import UUID

from pydantic import BaseModel

class DeviceInfoRequestModel(BaseModel):
    user_agent: str = ""
    platform: str = ""
    app_version: str = ""
    os: str = ""
    browser: str = ""
    is_mobile: bool = False

    def to_json(self) -> dict:
        return {
            "user_agent": self.user_agent,
            "platform": self.platform,
            "app_version": self.app_version,
            "os": self.os,
            "browser": self.browser,
            "is_mobile": self.is_mobile,
        }
    
class UserRequestModel(BaseModel):
    user_id: Optional[UUID] = None
    user_name: str = ""
    IP: str = ""
    device_info: Optional[DeviceInfoRequestModel] = DeviceInfoRequestModel()

    def to_json(self) -> dict:
        return {
            "user_id": str(self.user_id) if self.user_id else None,
            "user_name": self.user_name,
            "IP": self.IP,
            "device_info": self.device_info.to_json(),
        }