from pydantic import BaseModel
from typing import Optional
from uuid import UUID

class DeviceInfoRequestModel(BaseModel):
    user_agent: str
    platform: str
    app_version: str
    os: str
    browser: str
    is_mobile: bool

class UserRequestModel(BaseModel):
    user_id: Optional[UUID]
    user_name: str
    IP: str #TODO: should be moved to device_info
    device_info: DeviceInfoRequestModel