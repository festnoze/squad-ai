from abc import ABC, abstractmethod

class CalendarClientInterface(ABC):
    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with the calendar service and return success status"""
        pass

    @abstractmethod
    async def _ensure_authenticated_async(self):
        """Ensure the client is authenticated before making API calls"""
        pass

    @abstractmethod
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
        max_retries: int = 2,
        retry_delay: float = 1.0,
    ) -> str | None:
        """Create an event in the calendar system and return the event ID if successful

        Args:
            subject: The subject/title of the event
            start_datetime: Start date and time in ISO format (e.g., '2025-05-20T14:00:00Z')
            duration_minutes: Duration of the event in minutes (default: 60)
            description: Optional description of the event
            location: Optional location of the event
            owner_id: Optional Salesforce ID of the event owner
            what_id: Optional ID of related object (Account, Opportunity, etc.)
            who_id: Optional ID of associated person (Contact, Lead)
            max_retries: Maximum number of retry attempts if verification fails (default: 2)
            retry_delay: Delay in seconds before recursive retry attempt (default: 1.0)

        Returns:
            The ID of the created event if successful, None otherwise
        """
        pass

    @abstractmethod
    async def get_scheduled_appointments_async(self, start_datetime: str, end_datetime: str, owner_id: str | None = None, user_id: str | None = None) -> list[dict]:
        """Get events from calendar between specified start and end datetimes

        Args:
            start_datetime: Start date and time in ISO format (e.g., '2025-05-20T14:00:00Z')
            end_datetime: End date and time in ISO format (e.g., '2025-05-20T15:00:00Z')
            owner_id: Optional calendar owner ID to filter events by owner
            user_id: Optional user ID to filter events by user

        Returns:
            List of events if successful, None otherwise
        """
        pass

    @abstractmethod
    async def verify_appointment_existance_async(self, event_id: str | None = None, expected_subject: str | None = None, start_datetime: str = "", duration_minutes: int = 30) -> str | None:
        """Check if an appointment exists based on provided criteria

        Args:
            event_id: The ID of a specific event to verify (optional)
            expected_subject: The expected subject of the appointment (optional)
            start_datetime: Expected start date and time in ISO format (e.g., '2025-05-20T14:00:00Z')
            duration_minutes: Expected duration in minutes (default: 30)

        Returns:
            - If event_id is specified: returns event_id if found and matches criteria, None otherwise
            - If expected_subject is specified: returns event_id of the first appointment matching subject, None if not found
            - If neither is specified: returns event_id of the first appointment found in time window, None if none found
        """
        pass

    @abstractmethod
    async def delete_event_by_id_async(self, event_id: str) -> bool:
        """Delete an event from calendar by its ID

        Args:
            event_id: The ID of the event to delete

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_appointment_slots_async(
        self,
        start_datetime: str,
        end_datetime: str,
        work_type_id: str | None = None,
        service_territory_id: str | None = None,
    ) -> list[dict] | None:
        """
        Get available appointment slots using Lightning Scheduler API.
        
        Args:
            start_datetime: Start date and time in ISO format (e.g., '2025-05-20T14:00:00Z')
            end_datetime: End date and time in ISO format (e.g., '2025-05-20T15:00:00Z')
            work_type_id: Work Type ID for the appointment (optional)
            service_territory_id: Service Territory ID (optional)
            
        Returns:
            List of available appointment slots if successful, None otherwise
        """
        pass

    @abstractmethod
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
        """
        Create a ServiceAppointment using Lightning Scheduler and return the appointment ID if successful.
        
        Args:
            subject: The subject/title of the appointment
            start_datetime: Start date and time in ISO format (e.g., '2025-05-20T14:00:00Z')
            duration_minutes: Duration of the appointment in minutes (default: 30)
            description: Optional description of the appointment
            contact_id: Contact ID to associate with the appointment
            work_type_id: Work Type ID (optional)
            service_territory_id: Service Territory ID (optional) 
            parent_record_id: Parent record ID (Work Order, etc.)
            max_retries: Maximum number of retry attempts if verification fails
            retry_delay: Delay in seconds before retry attempt
            
        Returns:
            The ID of the created ServiceAppointment if successful, None otherwise
        """
        pass