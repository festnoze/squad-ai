"""Pydantic request models for the CMS module.

OWNED BY: backend-cms agent. Shapes per docs/CONTRACTS.md section 1.3 and
docs/decisions-cms.md sections 1-3. Invalid field descriptors (bad type, bad
key format, duplicate keys, select without options) fail here, producing
FastAPI's standard 422 body.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

FieldType = Literal["text", "richtext", "number", "boolean", "date", "image", "select"]

KEY_PATTERN = r"^[a-z][a-z0-9_]*$"


class FieldDescriptor(BaseModel):
    key: str = Field(pattern=KEY_PATTERN)
    label: str
    type: FieldType
    required: bool = False
    options: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_options(self):
        if self.type == "select":
            if not self.options:
                raise ValueError("select fields require a non-empty options list")
        else:
            self.options = []
        return self


def _check_unique_keys(fields: list[FieldDescriptor]) -> None:
    keys = [f.key for f in fields]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate field keys are not allowed")


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1)
    slug: str | None = None
    fields: list[FieldDescriptor] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_fields(self):
        _check_unique_keys(self.fields)
        return self


class CollectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    slug: str | None = None
    fields: list[FieldDescriptor] | None = None

    @model_validator(mode="after")
    def _check_fields(self):
        if self.fields is not None:
            _check_unique_keys(self.fields)
        return self


class EntryCreate(BaseModel):
    """Body for entry create and full-replacement update."""

    data: dict
