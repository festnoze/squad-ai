from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID

class UserRequestModel(BaseModel):
    user_id: Optional[UUID]
    user_name: str
    IP: str
    device_info: str