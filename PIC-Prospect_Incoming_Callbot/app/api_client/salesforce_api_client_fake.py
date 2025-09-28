import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from .calendar_client_interface import CalendarClientInterface
from .salesforce_user_client_interface import SalesforceUserClientInterface


class SalesforceApiClientFake(CalendarClientInterface, SalesforceUserClientInterface):
    """A dummy implementation of ``CalendarClientInterface`` and ``SalesforceUserClientInterface`` used for local
    testing.  Every method returns deterministic fake objects that satisfy the
    expectations encoded in *tests/api_client/salesforce_api_client_test.py*.
    """

    # --- Set-up -----------------------------------------------------------------
    def __init__(
        self,
        client_id: str | None = None,
        username: str | None = None,
        private_key_file: str | None = None,
        is_sandbox: bool = True,
    ) -> None:
        self.logger = logging.getLogger(__name__)

        # Very small bit of state so tests that poke at these attrs keep working
        self._access_token: str | None = None
        self._instance_url: str | None = None

        # Perform a fake eager authentication so the token & url are already set
        self.authenticate()

    # --- Authentication ---------------------------------------------------------
    def authenticate(self) -> bool:
        """Pretend to authenticate and create dummy access details."""
        self._access_token = "fake_access_token"
        self._instance_url = "https://fake.my.salesforce.com"
        return True

    async def _ensure_authenticated_async(self) -> None:
        """No-op helper that guarantees a token is present."""
        if not (self._access_token and self._instance_url):
            self.authenticate()

    # --- Calendar ---------------------------------------------------------------
    async def schedule_new_appointment_async(
        self,
        subject: str,
        start_datetime: str,
        duration_minutes: int = 60,
        description: str | None = None,
        location: str | None = None,
        owner_id: str | None = None,
        what_id: str | None = None,
        who_id: str | None = None,
    ) -> str | None:
        """Return a fabricated Salesforce Event Id."""
        await self._ensure_authenticated_async()
        # Anything that looks like a Salesforce 18-char id is fine for the tests
        return "EVT" + uuid.uuid4().hex[:15].upper()

    async def get_scheduled_appointments_async(self, start_datetime: str, end_datetime: str, owner_id: str | None = None, user_id: str | None = None) -> list[dict]:
        """Return at least one dummy appointment so `any(appointments)` is True."""
        await self._ensure_authenticated_async()

        is_btw_time_less_one_hour = datetime.strptime(end_datetime, "%Y-%m-%dT%H:%M:%SZ") - datetime.strptime(
            start_datetime, "%Y-%m-%dT%H:%M:%SZ"
        ) < timedelta(hours=1)
        if is_btw_time_less_one_hour:
            return []

        return [
            {
                "Id": "EVT000000000001",
                "Subject": "Fake Meeting",
                "Description": "Fake Meeting Description",
                "StartDateTime": start_datetime,
                "EndDateTime": (
                    (datetime.strptime(start_datetime, "%Y-%m-%dT%H:%M:%SZ") + timedelta(minutes=30)).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    )
                ),
            }
        ]

    async def delete_event_by_id_async(self, event_id: str) -> bool:
        await self._ensure_authenticated_async()
        return True

    async def verify_appointment_existance_async(self, event_id: str | None = None, expected_subject: str | None = None, start_datetime: str = "", duration_minutes: int = 30) -> str | None:
        await self._ensure_authenticated_async()
        # Return None to simulate no existing appointment found
        return None

    async def get_appointment_slots_async(
        self,
        start_datetime: str,
        end_datetime: str,
        work_type_id: str | None = None,
        service_territory_id: str | None = None,
    ) -> list[dict] | None:
        await self._ensure_authenticated_async()
        # Return fake available slots
        return [
            {
                "startTime": start_datetime,
                "endTime": end_datetime,
                "id": "SLOT" + uuid.uuid4().hex[:10].upper()
            }
        ]

    async def schedule_new_appointment_with_lightning_scheduler_async(
        self,
        subject: str,
        start_datetime: str,
        duration_minutes: int = 30,
        description: str | None = None,
        contact_id: str | None = None,
        work_type_id: str | None = None,
        service_territory_id: str | None = None,
        parent_record_id: str | None = None,
        max_retries: int = 2,
        retry_delay: float = 1.0,
    ) -> str | None:
        await self._ensure_authenticated_async()
        # Return a fake ServiceAppointment ID
        return "SA" + uuid.uuid4().hex[:16].upper()

    # --- People -----------------------------------------------------------------
    async def get_person_by_phone_async(self, phone_number: str) -> dict[str, Any] | None:  # type: ignore[override]
        """Return a fake Contact whose phone matches the query."""
        await self._ensure_authenticated_async()

        return {
            "type": "Contact",
            "data": {
                "Id": "003000000000001",
                "Phone": phone_number,
                "MobilePhone": phone_number,
                "Salutation": "Mr.",
                "FirstName": "Jean",
                "LastName": "Dupont",
                "Owner": {"Name": "Alice Martin"},
                # Add more fields if your downstream code expects them
            },
        }

    async def get_persons_async(self) -> list[dict[str, Any]]:  # type: ignore[override]
        await self._ensure_authenticated_async()
        return [
            {
                "type": "Contact",
                "Id": "003000000000002",
                "FirstName": "Jane",
                "LastName": "Doe",
            }
        ]

    async def get_leads_by_details_async(
        self,
        email: str | None = None,
        company_name: str | None = None,
        phone: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> list[dict[str, Any]] | None:
        """Return a fake lead list; if company_name == 'Studi' include one lead."""
        await self._ensure_authenticated_async()

        if company_name == "Studi":
            return [
                {
                    "Id": "00Q000000000001",
                    "Company": "Studi",
                    "Phone": phone or "+33600000000",
                    "IsConverted": False,
                }
            ]
        # Default: empty list (valid behaviour for tests)
        return []

    async def get_opportunities_by_contact_async(self, contact_id: str) -> list[dict] | None:
        """Return fake opportunities for a contact."""
        await self._ensure_authenticated_async()
        return [
            {
                "Id": "006000000000001",
                "Name": "Fake Opportunity",
                "StageName": "Prospecting",
                "Amount": 5000,
                "OwnerId": "005000000000001",
                "Owner": {"Name": "Alice Martin"}
            }
        ]

    async def get_opportunities_for_lead_async(self, lead_id: str) -> list[dict] | None:
        """Return fake opportunities for a lead."""
        await self._ensure_authenticated_async()
        # Most leads don't have converted opportunities
        return []

    async def get_user_by_id_async(self, user_id: str) -> dict | None:
        """Return fake user information."""
        await self._ensure_authenticated_async()
        return {
            "Id": user_id,
            "Name": "Alice Martin",
            "FirstName": "Alice",
            "LastName": "Martin",
            "Email": "alice.martin@fake.com",
            "Phone": "+33600000001",
            "Title": "Sales Manager",
            "IsActive": True
        }

    async def get_complete_contact_info_by_phone_async(self, phone_number: str) -> dict | None:
        """Return complete fake contact information."""
        await self._ensure_authenticated_async()
        
        # Get basic person info
        person_data = await self.get_person_by_phone_async(phone_number)
        if not person_data:
            return None
            
        contact_info = person_data.get("data")
        person_type = person_data.get("type")
        
        # Get opportunities based on type
        opportunities = []
        if person_type == "Contact" and contact_info:
            opportunities = await self.get_opportunities_by_contact_async(contact_info.get("Id"))
        elif person_type == "Lead" and contact_info:
            opportunities = await self.get_opportunities_for_lead_async(contact_info.get("Id"))
            
        # Get user info
        owner_id = contact_info.get("Owner", {}).get("Id") if contact_info else None
        assigned_user = None
        if owner_id:
            assigned_user = await self.get_user_by_id_async(owner_id)
            
        return {
            "contact": contact_info,
            "contact_type": person_type,
            "opportunities": opportunities or [],
            "most_recent_opportunity": opportunities[0] if opportunities else None,
            "assigned_user": assigned_user,
            "user_source": "contact" if assigned_user else None
        }

    async def get_phone_numbers_async(self, limit: int = 10) -> list[dict] | None:
        """Return fake phone numbers."""
        await self._ensure_authenticated_async()
        return [
            {
                "phone_number": "+33600000000",
                "type": "Contact",
                "person_id": "003000000000001",
                "first_name": "Jean",
                "last_name": "Dupont",
                "email": "jean.dupont@fake.com",
                "phone_type": "Phone"
            },
            {
                "phone_number": "+33600000001",
                "type": "Lead",
                "person_id": "00Q000000000001",
                "first_name": "Marie",
                "last_name": "Martin",
                "email": "marie.martin@fake.com",
                "company": "Fake Company",
                "phone_type": "MobilePhone"
            }
        ][:limit]

    # --- Metadata ---------------------------------------------------------------
    async def discover_database_async(
        self,
        sobjects_to_describe: list[str] | None = None,
        include_fields: bool = True,
    ) -> dict[str, Any] | None:
        await self._ensure_authenticated_async()
        return {"Account": {"fields": {}}, "Contact": {"fields": {}}}
