import uuid
from uuid import UUID
from datetime import datetime

class User:
    id: UUID
    name: str
    ip: str
    device_info: str
    created_at: datetime

    def __init__(self, name: str, ip: str, device_info: str, created_at: datetime = None, id: UUID = None) -> None:
        self.id = id if id else uuid.uuid4()
        self.name = name
        self.ip = ip
        self.device_info = device_info
        self.created_at = created_at if created_at else datetime.now(datetime.timezone.utc)