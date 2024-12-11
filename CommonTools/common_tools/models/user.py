from typing import Optional
import uuid
from uuid import UUID
from datetime import datetime

class User:
    id: UUID
    name: str
    ip: str
    device_info: str
    created_at: datetime

    def __init__(self, name: str, ip: str, device_info: str, created_at: datetime = None, id: Optional[UUID] = None) -> None:
        self.id = id if id is not None else uuid.uuid4()
        self.name = name
        self.ip = ip
        self.device_info = device_info
        self.created_at = created_at