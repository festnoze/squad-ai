"""JWT Payload Model

This module defines the Pydantic model for decoded JWT payloads.
"""

from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class JWTSkillForgePayload(BaseModel):
    """Model representing a decoded JWT token payload from Studi LMS.

    This model contains the standard JWT claims and custom claims
    specific to the SkillForge application and Studi LMS.

    Standard JWT Claims:
        iss: Issuer (e.g., "uat-lms-studi.studi.fr")
        exp: Expiration time (unix timestamp)
        nbf: Not before time (unix timestamp)

    Studi LMS Claims:
        sid: Session ID / User ID (UUID string)
        client: Client ID (integer)
        schoolId: School ID (integer)

    Example payload:
        {
            "sid": "3039aaca-d954-4364-95e3-537f7f421c57",
            "client": 199520,
            "schoolId": 1009,
            "iss": "uat-lms-studi.studi.fr",
            "exp": 1760705630,
            "nbf": 1760697530
        }
    """

    # Standard JWT claims
    iss: str | None = None  # Issuer (e.g., "uat-lms-studi.studi.fr")
    exp: int | None = None  # Expiration time (unix timestamp)
    nbf: int | None = None  # Not before time (unix timestamp)

    # Studi LMS custom claims
    sid: str | UUID | None = None  # Session ID / User ID (UUID)
    client: int | None = None  # Client ID
    schoolId: int | None = None  # School ID (camelCase as per LMS format)

    # Additional optional claims (for backward compatibility or future use)
    roles: list[str] = []  # User roles (e.g., ['student', 'admin'])

    def get_token_uuid(self) -> UUID | None:
        """Convert sid (session/user ID) to UUID if present.

        Returns:
            UUID object or None if sid is not set
        """
        if self.sid is None:
            return None
        if isinstance(self.sid, UUID):
            return self.sid
        return UUID(self.sid)

    def get_lms_user_id(self) -> str | None:
        """Get the user ID.

        Returns:
            School ID as integer or None if not set
        """
        return str(self.client)

    def get_school_id(self) -> str | None:
        """Get the school ID.

        Returns:
            School ID as integer or None if not set
        """
        return str(self.schoolId)

    def get_school_name(self) -> str | None:
        """Get the school name extracted from the issuer URL.

        Extracts the school name from patterns like:
        - "uat-lms-studi.studi.fr" -> "Studi"
        - "uat-lms-foo.foo.fr" -> "Foo"

        Returns:
            School name as string (capitalized) or None if not set or cannot be extracted
        """
        if self.iss is None:
            return None

        # Split by dots and hyphens to extract the school name
        # Expected format: "uat-lms-<school>.<school>.fr"
        parts = self.iss.split(".")
        if len(parts) < 2:
            return self.iss

        # Try to extract from first part (e.g., "uat-lms-studi" -> "studi")
        first_part_segments = parts[0].split("-")
        if len(first_part_segments) >= 3:
            school_name = first_part_segments[-1]
            return school_name.capitalize()

        # Fallback: use second part if first approach fails
        return parts[1].capitalize() if len(parts) > 1 else None

    def get_issuer(self) -> str | None:
        """Get the issuer.

        Returns:
            Issuer as string or None if not set
        """
        return self.iss

    def get_token_expiration(self) -> datetime | None:
        """Get the token expiration time.

        Returns:
            Expiration time as datetime or None if not set
        """
        if self.exp is None:
            return None
        return datetime.fromtimestamp(self.exp)

    def get_token_not_before(self) -> datetime | None:
        """Get the token not before time.

        Returns:
            Not before time as datetime or None if not set
        """
        if self.nbf is None:
            return None
        return datetime.fromtimestamp(self.nbf)

    def is_expired(self) -> bool:
        """Check if the token is expired based on the exp claim.

        Returns:
            True if expired, False otherwise
        """
        if self.exp is None:
            return False
        return datetime.fromtimestamp(self.exp) < datetime.now()

    def is_not_yet_valid(self) -> bool:
        """Check if the token is not yet valid based on the nbf claim.

        Returns:
            True if not yet valid, False otherwise
        """
        if self.nbf is None:
            return False
        return datetime.fromtimestamp(self.nbf) > datetime.now()

    def has_role(self, role: str) -> bool:
        """Check if the user has a specific role.

        Args:
            role: Role name to check

        Returns:
            True if user has the role, False otherwise
        """
        return role in self.roles
