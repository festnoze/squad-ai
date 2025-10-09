from typing import Any

from pydantic import BaseModel, Field


class CreateContactRequest(BaseModel):
    first_name: str = Field(..., description="Contact's first name")
    last_name: str = Field(..., description="Contact's last name")
    email: str | None = Field(None, description="Contact's email address")
    phone: str | None = Field(None, description="Contact's phone number")
    mobile_phone: str | None = Field(None, description="Contact's mobile phone number")
    account_id: str | None = Field(None, description="ID of the Account to associate with the contact")
    owner_id: str | None = Field(None, description="ID of the User who will own this contact")
    title: str | None = Field(None, description="Contact's job title")
    department: str | None = Field(None, description="Contact's department")
    description: str | None = Field(None, description="Additional description or notes")
    additional_fields: dict[str, Any] | None = Field(default_factory=dict, description="Any additional custom fields")

    def to_dict(self) -> dict[str, Any]:
        result = {
            "first_name": self.first_name,
            "last_name": self.last_name
        }

        if self.email:
            result["email"] = self.email
        if self.phone:
            result["phone"] = self.phone
        if self.mobile_phone:
            result["mobile_phone"] = self.mobile_phone
        if self.account_id:
            result["account_id"] = self.account_id
        if self.owner_id:
            result["owner_id"] = self.owner_id
        if self.title:
            result["title"] = self.title
        if self.department:
            result["department"] = self.department
        if self.description:
            result["description"] = self.description

        if self.additional_fields:
            result.update(self.additional_fields)

        return result


class CreateOpportunityRequest(BaseModel):
    name: str = Field(..., description="Opportunity name")
    stage_name: str = Field(..., description="Sales stage name (e.g., 'Prospecting', 'Qualification', 'Closed Won')")
    close_date: str = Field(..., description="Expected close date in YYYY-MM-DD format")
    account_id: str | None = Field(None, description="ID of the Account associated with the opportunity")
    owner_id: str | None = Field(None, description="ID of the User who will own this opportunity")
    contact_id: str | None = Field(None, description="ID of the Contact to link directly to this opportunity")
    contact_role: str | None = Field("Decision Maker", description="Role of the contact in the opportunity")
    converted_from_lead_id: str | None = Field(None, description="ID of the Lead this opportunity was converted from")
    amount: float | None = Field(None, description="Opportunity amount/value")
    probability: int | None = Field(None, ge=0, le=100, description="Probability percentage (0-100)")
    description: str | None = Field(None, description="Opportunity description")
    lead_source: str | None = Field(None, description="Lead source (e.g., 'Web', 'Phone Inquiry', 'Partner Referral')")
    type_: str | None = Field(None, alias="type", description="Opportunity type (e.g., 'Existing Customer - Upgrade', 'New Customer')")
    next_step: str | None = Field(None, description="Next step in the sales process")
    additional_fields: dict[str, Any] | None = Field(default_factory=dict, description="Any additional custom fields")

    class Config:
        allow_population_by_field_name = True

    def to_dict(self) -> dict[str, Any]:
        result = {
            "name": self.name,
            "stage_name": self.stage_name,
            "close_date": self.close_date
        }

        if self.account_id:
            result["account_id"] = self.account_id
        if self.owner_id:
            result["owner_id"] = self.owner_id
        if self.contact_id:
            result["contact_id"] = self.contact_id
        if self.contact_role:
            result["contact_role"] = self.contact_role
        if self.converted_from_lead_id:
            result["converted_from_lead_id"] = self.converted_from_lead_id
        if self.amount is not None:
            result["amount"] = self.amount
        if self.probability is not None:
            result["probability"] = self.probability
        if self.description:
            result["description"] = self.description
        if self.lead_source:
            result["lead_source"] = self.lead_source
        if self.type_:
            result["type_"] = self.type_
        if self.next_step:
            result["next_step"] = self.next_step

        if self.additional_fields:
            result.update(self.additional_fields)

        return result


class AddContactRoleRequest(BaseModel):
    opportunity_id: str = Field(..., description="ID of the Opportunity")
    contact_id: str = Field(..., description="ID of the Contact")
    role: str = Field("Decision Maker", description="Role of the contact (e.g., 'Decision Maker', 'Influencer', 'Economic Buyer')")
    is_primary: bool = Field(False, description="Whether this should be the primary contact for the opportunity")


class SalesforceResponse(BaseModel):
    success: bool = Field(..., description="Whether the operation was successful")
    id: str | None = Field(None, description="ID of the created/modified record")
    message: str = Field(..., description="Status message")
    details: dict[str, Any] | None = Field(None, description="Additional details about the operation")

    @classmethod
    def success_response(cls, record_id: str, message: str, details: dict[str, Any] | None = None):
        return cls(success=True, id=record_id, message=message, details=details)

    @classmethod
    def error_response(cls, message: str, details: dict[str, Any] | None = None):
        return cls(success=False, message=message, details=details)
