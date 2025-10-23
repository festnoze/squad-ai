from models.base_model import IdStatefulBaseModel


class School(IdStatefulBaseModel):
    """School model representing a school in the system.

    Inherits common fields (id, created_at, updated_at, deleted_at) from IdStatefulBaseModel.

    Attributes:
        name: Name of the school
        address: Physical address of the school
        city: City where the school is located
        postal_code: Postal/ZIP code of the school
        country: Country where the school is located
        phone: Contact phone number
        email: Contact email address
    """

    name: str
    address: str | None = None
    city: str | None = None
    postal_code: str | None = None
    country: str | None = None
    phone: str | None = None
    email: str | None = None
