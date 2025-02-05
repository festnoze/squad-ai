from typing import Optional
import uuid
from uuid import UUID
from datetime import datetime
from common_tools.models.device_info import DeviceInfo

class User:
    id: UUID
    name: str
    device_info: DeviceInfo
    created_at: datetime

    def __init__(self, name: str = '', device_info: DeviceInfo = None, id: Optional[UUID] = None, created_at: datetime = None) -> None:
        self.name = name
        self.device_info = device_info
        self.created_at = created_at
        self.id = id #if id is not None else uuid.uuid4()