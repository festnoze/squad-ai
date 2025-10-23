"""Token Response Models

This module defines response models for JWT token operations.
"""

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    """Response model for JWT token creation.

    Attributes:
        token: The generated JWT token string
        token_type: Token type (always "Bearer")
        expires_in_hours: Token expiration time in hours
        created_at: Token creation timestamp
        sid: Session/User ID (UUID)
        client: Client ID
        school_id: School ID
        issuer: Issuer

    Example:
        {
            "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "token_type": "Bearer",
            "expires_in_hours": 24,
            "created_at": "2025-01-17T10:30:00",
            "sid": "3039aaca-d954-4364-95e3-537f7f421c57",
            "client": 199520,
            "school_id": 1009,
            "issuer": "uat-lms-studi.studi.fr"
        }
    """

    token: str = Field(..., description="JWT token string")
    token_type: str = Field("Bearer", description="Token type")
    expires_in_hours: int = Field(..., description="Token expiration time in hours")
    created_at: str = Field(..., description="Token creation timestamp")
    sid: str = Field(..., description="Session/User ID (UUID)")
    client: int = Field(..., description="Client ID")
    school_id: int = Field(..., description="School ID", alias="schoolId")
    issuer: str = Field(..., description="Issuer")

    class Config:
        populate_by_name = True  # Allow both snake_case and camelCase
