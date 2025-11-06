import json
from datetime import datetime
from typing import Any
from uuid import UUID


class UUIDEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles UUID and datetime objects."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)
