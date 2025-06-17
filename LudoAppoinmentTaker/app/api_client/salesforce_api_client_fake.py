import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .salesforce_api_client_interface import SalesforceApiClientInterface


class SalesforceApiClientFake(SalesforceApiClientInterface):
    """A dummy implementation of ``SalesforceApiClientInterface`` used for local
    testing.  Every method returns deterministic fake objects that satisfy the
    expectations encoded in *tests/api_client/salesforce_api_client_test.py*.
    """

    # --- Set-up -----------------------------------------------------------------
    def __init__(
        self,
        client_id: Optional[str] = None,
        username: Optional[str] = None,
        private_key_file: Optional[str] = None,
        is_sandbox: bool = True,
    ) -> None:
        self.logger = logging.getLogger(__name__)

        # Very small bit of state so tests that poke at these attrs keep working
        self._access_token: Optional[str] = None
        self._instance_url: Optional[str] = None

        # Perform a fake eager authentication so the token & url are already set
        self.authenticate()

    # --- Authentication ---------------------------------------------------------
    def authenticate(self) -> bool:
        """Pretend to authenticate and create dummy access details."""
        self._access_token = "fake_access_token"
        self._instance_url = "https://fake.my.salesforce.com"
        return True

    async def _ensure_authenticated_async(self) -> None:  # noqa: D401
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

    async def get_scheduled_appointments_async(
        self,
        start_datetime: str,
        end_datetime: str,
        owner_id: str | None = None,
    ) -> List[Dict[str, Any]] | None:
        """Return at least one dummy appointment so `any(appointments)` is True."""
        await self._ensure_authenticated_async()
        
        is_btw_time_less_one_hour = datetime.strptime(end_datetime, "%Y-%m-%dT%H:%M:%SZ") - datetime.strptime(start_datetime, "%Y-%m-%dT%H:%M:%SZ") < timedelta(hours=1)
        if is_btw_time_less_one_hour: return []
        
        return [
            {
                "Id": "EVT000000000001",
                "Subject": "Fake Meeting",
                "Description": "Fake Meeting Description",
                "StartDateTime": start_datetime,
                "EndDateTime": (
                    (datetime.strptime(start_datetime, "%Y-%m-%dT%H:%M:%SZ") + timedelta(minutes=30))
                    .strftime("%Y-%m-%dT%H:%M:%SZ")
                ),
            }
        ]

    # --- People -----------------------------------------------------------------
    async def get_person_by_phone_async(self, phone_number: str) -> Dict[str, Any] | None:  # type: ignore[override]
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

    async def get_persons_async(self) -> List[Dict[str, Any]]:  # type: ignore[override]
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
    ) -> List[Dict[str, Any]] | None:
        """Return a fake lead list; if company_name == 'Studi' include one lead."""
        await self._ensure_authenticated_async()

        if company_name == "Studi":
            return [
                {
                    "Id": "00Q000000000001",
                    "Company": "Studi",
                    "Phone": phone or "+33668422388",
                    "IsConverted": False,
                }
            ]
        # Default: empty list (valid behaviour for tests)
        return []

    # --- Metadata ---------------------------------------------------------------
    async def discover_database_async(
        self,
        sobjects_to_describe: List[str] | None = None,
        include_fields: bool = True,
    ) -> Dict[str, Any] | None:
        await self._ensure_authenticated_async()
        return {"Account": {"fields": {}}, "Contact": {"fields": {}}}

