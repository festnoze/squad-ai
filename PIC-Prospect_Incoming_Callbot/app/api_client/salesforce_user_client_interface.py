from abc import ABC, abstractmethod


class SalesforceUserClientInterface(ABC):
    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with Salesforce using JWT and return success status"""
        pass

    @abstractmethod
    async def _ensure_authenticated_async(self):
        """Ensure the client is authenticated before making API calls"""
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
        Retrieve latest Contacts and Leads from Salesforce (asynchronous).

        Returns:
            A list of dictionaries containing the person's type ('Contact' or 'Lead') and data.
        """
        pass

    @abstractmethod
    async def get_leads_by_details_async(
        self,
        email: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        company_name: str | None = None,
    ) -> list[dict] | None:
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
    async def get_opportunities_by_contact_async(self, contact_id: str) -> list[dict] | None:
        """
        Retrieve Opportunities related to a specific Contact via Account relationship.
        
        Args:
            contact_id: The ID of the Salesforce Contact.
            
        Returns:
            A list of Opportunity dictionaries related to the contact's account, 
            or None if an error occurs. Returns empty list if no opportunities found.
        """
        pass

    @abstractmethod
    async def get_opportunities_for_lead_async(self, lead_id: str) -> list[dict] | None:
        """
        Retrieve Opportunities related to a specific Lead, primarily if converted (asynchronous).
        Args:
            lead_id: The ID of the Salesforce Lead.
        Returns:
            A list of Opportunity dictionaries. Prioritizes ConvertedOpportunityId,
            then searches by ConvertedAccountId. Returns None on error, empty list if no related Opps found.
        """
        pass

    @abstractmethod
    async def get_user_by_id_async(self, user_id: str) -> dict | None:
        """
        Retrieve detailed information about a Salesforce User by ID.
        
        Args:
            user_id: The ID of the Salesforce User.
            
        Returns:
            A dictionary containing user information, or None if user not found or error occurs.
        """
        pass

    @abstractmethod
    async def get_complete_contact_info_by_phone_async(self, phone_number: str) -> dict | None:
        """
        Aggregated method to retrieve complete contact information from a phone number.
        
        This method combines multiple sub-methods:
        1. Search for contact by phone number
        2. Get opportunities related to the contact
        3. Get the most recent opportunity
        4. Get user associated with the opportunity (or contact owner if no opportunity)
        
        Args:
            phone_number: The phone number to search for.
            
        Returns:
            A dictionary containing contact, opportunities, and user information,
            or None if no contact found or error occurs.
        """
        pass

    @abstractmethod
    async def get_phone_numbers_async(self, limit: int = 10) -> list[dict] | None:
        """
        Retrieve the first x phone numbers from both Contacts and Leads in Salesforce.
        
        Args:
            limit: Number of phone numbers to retrieve (default: 10)
            
        Returns:
            A list of dictionaries containing phone numbers and associated person data,
            or None if an error occurs.
        """
        pass

    @abstractmethod
    async def discover_database_async(
        self, sobjects_to_describe: list[str] | None = None, include_fields: bool = True
    ) -> dict | None:
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
