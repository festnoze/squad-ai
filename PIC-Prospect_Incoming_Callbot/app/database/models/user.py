from datetime import datetime
from uuid import UUID

from database.models.device_info import DeviceInfo


class User:
    id: UUID
    name: str
    device_info: DeviceInfo
    created_at: datetime

    def __init__(
        self, name: str = "", device_info: DeviceInfo = None, id: UUID | None = None, created_at: datetime = None
    ) -> None:
        self.name = name
        self.device_info = device_info
        self.created_at = created_at
        self.id = id  # if id is not None else uuid.uuid4()

    def __repr__(self) -> str:
        return f"User: {self.name} ({self.id})"

    def __str__(self) -> str:
        return self.__repr__()

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "device_info": self.device_info.to_dict() if self.device_info else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
