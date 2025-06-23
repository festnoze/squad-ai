
from abc import ABC, abstractmethod

class SalesforceApiClientInterface(ABC):
    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with Salesforce using JWT and return success status"""
        pass

    @abstractmethod
    async def _ensure_authenticated_async(self):
        pass

    @abstractmethod
    async def schedule_new_appointment_async(self, subject: str, start_datetime: str, duration_minutes: int = 60, description: str | None = None, 
                   location: str | None = None, owner_id: str | None = None, 
                   what_id: str | None = None, who_id: str | None = None) -> str | None:
        """Create an event in Salesforce and return the event ID if successful
        
        Args:
            subject: The subject/title of the event
            start_datetime: Start date and time in ISO format (e.g., '2025-05-20T14:00:00Z')
            duration_minutes: Duration of the event in minutes (default: 60)
            description: Optional description of the event
            location: Optional location of the event
            owner_id: Optional Salesforce ID of the event owner
            what_id: Optional ID of related object (Account, Opportunity, etc.)
            who_id: Optional ID of associated person (Contact, Lead)
            
        Returns:
            The ID of the created event if successful, None otherwise
        """        
        pass

    @abstractmethod
    async def get_scheduled_appointments_async(self, start_datetime: str, end_datetime: str, owner_id: str | None = None) -> list | None:
        """Get events from Salesforce calendar between specified start and end datetimes
        
        Args:
            start_datetime: Start date and time in ISO format (e.g., '2025-05-20T14:00:00Z')
            end_datetime: End date and time in ISO format (e.g., '2025-05-20T15:00:00Z')
            owner_id: Optional Salesforce ID to filter events by owner
            
        Returns:
            List of events if successful, None otherwise
        """
        pass

    @abstractmethod
    async def get_person_by_phone_async(self, phone_number: str) -> dict | None:
        """
        Retrieve a Contact or Lead from Salesforce by phone number (asynchronous).
        Searches Contacts first, then non-converted Leads if no Contact is found.

        Args:
            phone_number: The phone number to search for.

        Returns:
            A dictionary containing the person's type ('Contact' or 'Lead') and data,
            or None if no matching record is found.
        """
        pass

    @abstractmethod
    async def get_persons_async(self) -> list[dict]:
        """
        Retrieve lestest Contacts and Leads from Salesforce (asynchronous).

        Returns:
            A list of dictionaries containing the person's type ('Contact' or 'Lead') and data.
        """
        pass

    @abstractmethod
    async def get_leads_by_details_async(self, email: str | None = None, first_name: str | None = None, last_name: str | None = None, company_name: str | None = None) -> list[dict] | None:
        """
        Retrieve a list of Leads from Salesforce by details (asynchronous).

        Args:
            email: Optional email to search for.
            first_name: Optional first name to search for.
            last_name: Optional last name to search for.
            company_name: Optional company name to search for.

        Returns:
            A list of dictionaries containing the lead's data, or None if no matching record is found.
        """
        pass

    @abstractmethod
    async def discover_database_async(self, sobjects_to_describe: list[str] | None = None, include_fields: bool = True) -> dict | None:
        """
        Discovers the schema of Salesforce SObjects.

        Retrieves SObject names and for each, their fields (properties),
        identifying primary keys (Id field) and foreign keys (reference fields).

        Args:
            sobjects_to_describe: An optional list of SObject API names to describe.
                                  If None, attempts to describe all accessible SObjects.
                                  Warning: Describing all SObjects can be very slow and
                                  consume a significant number of API calls.
            include_fields: If True (default), includes all fields for each SObject.
                            If False, only includes primary key (Id) and foreign key fields.

        Returns:
            A dictionary where keys are SObject names. Each value is a dictionary
            containing a 'fields' key with field metadata, or an 'error' key
            if describing that SObject failed. Returns None if the initial SObject
            list cannot be fetched.
        """
        pass