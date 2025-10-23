from pydantic import EmailStr
from models.base_model import IdStatefulBaseModel
from models.school import School
from models.user_preference import UserPreference


class User(IdStatefulBaseModel):
    """User model representing a user in the system.

    Inherits common fields (id, created_at, updated_at, deleted_at) from BaseModelWithTimestamps.

    Attributes:
        school_lms_internal_user_id: Unique user identifier from LMS
        school: School this user belongs to (optional)
        preference: User preferences (one-to-one relationship, optional)
        civility: User's civility/title
        first_name: User's first name
        last_name: User's last name
        email: User's email address
    """

    lms_user_id: str
    school: School | None = None
    preference: UserPreference | None = None
    civility: str
    first_name: str
    last_name: str
    email: EmailStr
