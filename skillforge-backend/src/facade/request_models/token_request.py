"""Token Request Models

This module defines request models for JWT token generation.
"""

from pydantic import BaseModel, Field


class CreateTokenRequest(BaseModel):
    """Request model for creating a JWT token.

    Attributes:
        client: Client ID (integer)
        school_id: School ID (integer)
        issuer: Issuer string (e.g., "uat-lms-studi.studi.fr")
        expires_in_hours: Token expiration time in hours (default: 24)

    Example:
        {
            "client": 199520,
            "school_id": 1009,
            "issuer": "uat-lms-studi.studi.fr",
            "expires_in_hours": 24
        }
    """

    client: int = Field(..., description="Client ID", examples=[199520])
    school_id: int = Field(..., description="School ID", examples=[1009], alias="schoolId")
    issuer: str = Field(..., description="Issuer (e.g., uat-lms-studi.studi.fr)", examples=["uat-lms-studi.studi.fr"])
    expires_in_hours: int = Field(default=24, description="Token expiration time in hours", ge=1, le=8760, examples=[24])

    class Config:
        populate_by_name = True  # Allow both snake_case and camelCase
