"""Entry data validation against a collection's field descriptors.

OWNED BY: backend-cms agent. Rules per docs/decisions-cms.md section 2.

validate_entry_data is a pure sync function: the caller (the router) pre-fetches
the project's asset ids into a set so the image check needs no IO here.
"""

from datetime import date


def validate_entry_data(
    fields: list[dict], data: dict, asset_ids: set[int]
) -> list[dict]:
    """Return a list of {"field", "message"} error dicts (empty list = valid)."""
    errors: list[dict] = []
    known_keys = {f["key"] for f in fields}

    for key in data:
        if key not in known_keys:
            errors.append({"field": key, "message": "unknown field"})

    for field in fields:
        key = field["key"]
        ftype = field["type"]
        required = bool(field.get("required", False))
        options = field.get("options") or []
        value = data.get(key)

        if value is None:
            if required:
                errors.append({"field": key, "message": "field is required"})
            continue

        if ftype == "text":
            if not isinstance(value, str):
                errors.append({"field": key, "message": "must be a string"})
            elif required and not value.strip():
                errors.append({"field": key, "message": "field is required"})
        elif ftype == "richtext":
            if not isinstance(value, str):
                errors.append({"field": key, "message": "must be a string"})
            elif required and not value:
                errors.append({"field": key, "message": "field is required"})
        elif ftype == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append({"field": key, "message": "must be a number"})
        elif ftype == "boolean":
            if not isinstance(value, bool):
                errors.append({"field": key, "message": "must be a boolean"})
        elif ftype == "date":
            if not isinstance(value, str) or not _is_iso_date(value):
                errors.append(
                    {"field": key, "message": "must be an ISO date (YYYY-MM-DD)"}
                )
        elif ftype == "image":
            if isinstance(value, bool):
                errors.append(
                    {"field": key, "message": "must be an asset id or a url string"}
                )
            elif isinstance(value, int):
                if value not in asset_ids:
                    errors.append(
                        {"field": key, "message": "asset not found in this project"}
                    )
            elif isinstance(value, str):
                if not value:
                    errors.append(
                        {"field": key, "message": "must be a non-empty url string"}
                    )
            else:
                errors.append(
                    {"field": key, "message": "must be an asset id or a url string"}
                )
        elif ftype == "select":
            if not isinstance(value, str) or value not in options:
                errors.append(
                    {"field": key, "message": "must be one of the field options"}
                )

    return errors


def normalize_entry_data(fields: list[dict], data: dict) -> dict:
    """Every current schema key present (missing -> None); unknown keys dropped."""
    return {field["key"]: data.get(field["key"]) for field in fields}


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True
