"""
Studi LMS User API Models.

This module contains Pydantic models for the Studi LMS user API responses,
specifically for the /v2/profile/me endpoint.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from models.school import School
from models.user import User


class UserType(BaseModel):
    """User type information."""

    code: str
    label: str


class UserStatus(BaseModel):
    """User status information."""

    code: str
    label: str


class Address(BaseModel):
    """User address information."""

    num_voie: Optional[str] = Field(None, alias="numVoie")
    nom_voie: Optional[str] = Field(None, alias="nomVoie")
    type_voie_id: Optional[int] = Field(None, alias="typeVoieId")
    code_postal: Optional[str] = Field(None, alias="codePostal")
    ville: Optional[str] = Field(None, alias="ville")
    pays_id: Optional[int] = Field(None, alias="paysId")
    appartement: Optional[str] = Field(None, alias="appartement")
    escalier: Optional[str] = Field(None, alias="escalier")
    etage: Optional[str] = Field(None, alias="etage")
    batiment: Optional[str] = Field(None, alias="batiment")
    residence: Optional[str] = Field(None, alias="residence")
    complement: Optional[str] = Field(None, alias="complement")
    address_id: Optional[int] = Field(None, alias="addressId")


class PhoneNumber(BaseModel):
    """User phone number information."""

    phone_number: str = Field(alias="phoneNumber")
    code: str
    country_code: Optional[str] = Field(None, alias="countryCode")
    label: str
    phone_number_id: int = Field(alias="phoneNumberId")


class Promotion(BaseModel):
    """User promotion/parcours information."""

    promotion_id: int = Field(alias="promotionId")
    code_parcours: str = Field(alias="codeParcours")
    session: str
    parcours_id: int = Field(alias="parcoursId")
    code: str
    libelle: str
    titre_parcours: str = Field(alias="titreParcours")
    evaluation: bool
    has_internship: bool = Field(alias="hasInternship")


class StudiLmsUserInfoResponse(BaseModel):
    """Complete user profile from LMS API."""

    user_type: UserType = Field(alias="userType")
    lms_user_id: int = Field(alias="userId")
    contact_unique: str = Field(alias="contactUnique")
    civility: str
    last_name: str = Field(alias="lastName")
    first_name: str = Field(alias="firstName")
    date_of_birth: datetime = Field(alias="dateofBirth")
    pseudo: str
    profile_picture: str = Field(alias="profilePicture")
    cover_picture: str = Field(alias="coverPicture")
    email: str
    internal: bool
    user_status: UserStatus = Field(alias="userStatus")
    last_connection: datetime = Field(alias="lastConnection")
    total_connection_time_in_seconds: int = Field(alias="totalConnectionTimeInSeconds")
    registration_form_info: List = Field(default_factory=list, alias="registrationFormInfo")
    total_connection_time: str = Field(alias="totalConnectionTime")
    addresses: List[Address] = Field(default_factory=list)
    phone_numbers: List[PhoneNumber] = Field(default_factory=list, alias="phoneNumbers")
    promotions: List[Promotion] = Field(default_factory=list)

    def convert_to_user_model(self, school_name: str) -> User:
        """Get user model from LMS user profile."""
        user = User(
            lms_user_id=str(self.lms_user_id),
            school=School(name=school_name),
            preference=None,
            civility=self.civility,
            last_name=self.last_name,
            first_name=self.first_name,
            email=self.email,
            date_of_birth=self.date_of_birth,
            extra_info={
                "pseudo": self.pseudo,
                "internal": self.internal,
                "user_type": self.user_type.model_dump(),
                "user_status": self.user_status.model_dump(),
                "last_connection": self.last_connection.isoformat(),
                "total_connection_time_in_seconds": self.total_connection_time_in_seconds,
                "registration_form_info": self.registration_form_info,
                "total_connection_time": self.total_connection_time,
                "addresses": [addr.model_dump() for addr in self.addresses],
                "phone_numbers": [phone.model_dump() for phone in self.phone_numbers],
                "promotions": [promo.model_dump() for promo in self.promotions],
                "contact_unique": self.contact_unique,
                "profile_picture": self.profile_picture,
                "cover_picture": self.cover_picture,
            },
        )
        return user

    class Config:
        """Pydantic configuration."""

        populate_by_name = True  # Allow both field names and aliases
