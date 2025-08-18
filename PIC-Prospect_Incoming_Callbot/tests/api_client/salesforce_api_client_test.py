import pytest
import asyncio
import os
import logging
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timedelta
#
from app.api_client.salesforce_api_client import SalesforceApiClient
from app.api_client.salesforce_api_client_interface import SalesforceApiClientInterface
    
@pytest.fixture
def salesforce_api_client() -> SalesforceApiClientInterface:
    salesforce_api_client = SalesforceApiClient()
    return salesforce_api_client

def test_authenticate(salesforce_api_client: SalesforceApiClientInterface):
    """Test that the salesforce_api_client can authenticate with Salesforce"""
    assert salesforce_api_client._access_token is not None, "Access token should be available after initialization"
    assert salesforce_api_client._instance_url is not None, "Instance URL should be available after initialization"
    
    salesforce_api_client._access_token = None
    salesforce_api_client._instance_url = None
    result = salesforce_api_client.authenticate()
    assert result is True, "Re-authentication should succeed"
    assert salesforce_api_client._access_token is not None, "Access token should be available after re-authentication"
    assert salesforce_api_client._instance_url is not None, "Instance URL should be available after re-authentication"


async def test_get_person_by_phone_async(salesforce_api_client: SalesforceApiClientInterface):
    """Test retrieving a person by phone number"""
    phone_number = "+33668422388"
    result = await salesforce_api_client.get_person_by_phone_async(phone_number)
    
    logging.info(f"get_person_by_phone_async result: {result}")
    
    if result is not None:
        # We found a person
        assert 'type' in result, "Result should have a 'type' field"
        assert result['type'] in ['Contact', 'Lead'], "Type should be either 'Contact' or 'Lead'"
        assert 'data' in result, "Result should have a 'data' field"
        
        # Verify the data structure based on the type
        if result['type'] == 'Contact':
            assert 'Id' in result['data'], "Contact should have an Id"
            # Phone should match our search query (either in Phone or MobilePhone)
            phone_match = (result['data'].get('Phone') == phone_number or 
                            result['data'].get('MobilePhone') == phone_number)
            assert phone_match, "Contact phone should match the search query"
        
        elif result['type'] == 'Lead':
            assert 'Id' in result['data'], "Lead should have an Id"
            # Phone should match our search query (either in Phone or MobilePhone)
            phone_match = (result['data'].get('Phone') == phone_number or 
                            result['data'].get('MobilePhone') == phone_number)
            assert phone_match, "Lead phone should match the search query"
    else:
        # No person found - this is also a valid test result
        logging.info(f"No person found with phone number: {phone_number}")


async def test_get_leads_by_details_async(salesforce_api_client: SalesforceApiClientInterface):
    """Test retrieving leads by details including phone number"""
    # Use the specified phone number
    phone_number = "+33668422388"
    
    # First, try to get leads by phone number
    # Note: The API doesn't directly support phone search in get_leads_by_details_async
    # So we'll use other fields that might be associated with this phone number
    
    # Approach 1: Try with just the phone number (might not work as the method doesn't directly search by phone)
    # Try to find leads with email that might be associated with this phone number
    # This is just a test approach - in real usage, we'd need to know the email
    result = await salesforce_api_client.get_leads_by_details_async()
    
    # Log the result for debugging
    logging.info(f"get_leads_by_details_async initial result count: {len(result) if result is not None else 'None'}")
    
    # If we got results, let's try to find our phone number
    if result is not None and len(result) > 0:
        # Check if any lead has our phone number
        matching_leads = [lead for lead in result if 
                            lead.get('Phone') == phone_number or 
                            lead.get('MobilePhone') == phone_number]
        
        if matching_leads:
            logging.info(f"Found {len(matching_leads)} leads with phone number {phone_number}")
            for lead in matching_leads:
                assert 'Id' in lead, "Lead should have an Id"
                assert not lead.get('IsConverted', False), "Lead should not be converted"
        else:
            logging.info(f"No leads found with phone number {phone_number} in the initial results")
    
    # Approach 2: Try with some specific criteria that might match our phone number's owner
    # For example, try with a company name that might be associated with this phone
    result_by_company = await salesforce_api_client.get_leads_by_details_async(company_name="Studi")
    
    # Log the result for debugging
    logging.info(f"get_leads_by_details_async by company result count: {len(result_by_company) if result_by_company is not None else 'None'}")
    
    # Check if we got valid results
    if result_by_company is not None:
        assert isinstance(result_by_company, list), "Result should be a list"
        # If we got results, verify their structure
        for lead in result_by_company:
            assert 'Id' in lead, "Lead should have an Id"
            assert 'Company' in lead, "Lead should have a Company field"
            assert lead['Company'] == "Studi", "Company should match our search criteria"


async def test_schedule_new_appointment_async(salesforce_api_client: SalesforceApiClientInterface):
    """Test scheduling a new appointment"""
    now = datetime.now()
    start_datetime = now + timedelta(days=1)  # Tomorrow
    start_datetime_str = start_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    subject = "Test Appointment from Automated Tests"
    description = "This is a test appointment created by automated tests. Please ignore."
    owner_id = '005Aa00000K990ZIAR'
    who_id = '003Aa00000jW2RBIA0'

    # Schedule the appointment
    event_id = await salesforce_api_client.schedule_new_appointment_async(
                        subject=subject,
                        start_datetime=start_datetime_str,
                        duration_minutes=30,
                        description=description,
                        owner_id=owner_id,
                        who_id=who_id)
    
    # Verify we got an event ID back
    assert event_id is not None, "Should receive an event ID when scheduling an appointment"
    assert isinstance(event_id, str), "Event ID should be a string"
    
    # Delete the created event ID
    assert await salesforce_api_client.delete_event_by_id_async(event_id)


@pytest.mark.parametrize("fixed_date", [
    True,
    #False
])
async def test_get_scheduled_appointments_async(salesforce_api_client: SalesforceApiClientInterface, fixed_date: bool):
    """Test retrieving scheduled appointments"""
    # Get appointments for the next 7 days
    if fixed_date:
        start_datetime = "2025-06-01T00:00:00Z"
        end_datetime = "2025-06-15T23:59:59Z"
    else:
        now = datetime.now()
        start_datetime = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_datetime = (now + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    owner_id = '005Aa00000K990ZIAR'
    
    # Get appointments without specifying an owner
    appointments = await salesforce_api_client.get_scheduled_appointments_async(
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        owner_id=owner_id
    )
    
    # Verify we got a valid response
    assert appointments is not None, "Should receive a list of appointments"
    assert isinstance(appointments, list), "Appointments should be a list"
    assert any(appointments), "Should receive at least one appointment"
    
    # Log the number of appointments found
    logging.info(f"Found {len(appointments)} appointments in the next 7 days")
    
    # Verify the structure of appointments if any were found
    if appointments:
        for appointment in appointments:
            assert 'Id' in appointment, "Appointment should have an Id"
            assert 'Subject' in appointment, "Appointment should have a Subject"
            assert 'StartDateTime' in appointment, "Appointment should have a StartDateTime"
            assert 'EndDateTime' in appointment, "Appointment should have an EndDateTime"


async def test_get_persons_async(salesforce_api_client: SalesforceApiClientInterface):
    """Test retrieving persons (contacts)"""
    # Get the latest contacts
    contacts = await salesforce_api_client.get_persons_async()
    
    # Verify we got a valid response
    assert contacts is not None, "Should receive a list of contacts"
    assert isinstance(contacts, list), "Contacts should be a list"
    
    # Log the number of contacts found
    logging.info(f"Found {len(contacts)} contacts")
    
    # Verify the structure of contacts if any were found
    if contacts:
        for contact in contacts:
            assert 'Id' in contact, "Contact should have an Id"


@pytest.fixture
def mock_salesforce_client():
    """Create a mock Salesforce client for unit testing"""
    client = SalesforceApiClient()
    client._access_token = "mock_token"
    client._instance_url = "https://mock-instance.salesforce.com"
    return client


class TestCheckForAppointmentCreation:
    """Unit tests for check_for_appointment_creation method"""
    
    async def test_check_for_appointment_creation_with_valid_event_id(self):
        """Test successful verification with a valid event_id"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        # Mock the get_scheduled_appointments_async method
        mock_appointments = [
            {
                'Id': 'event_123',
                'Subject': 'Test Meeting',
                'StartDateTime': '2025-05-20T14:00:00+02:00',
                'EndDateTime': '2025-05-20T15:00:00+02:00'
            }
        ]
        
        with patch.object(client, 'get_scheduled_appointments_async', new_callable=AsyncMock) as mock_get_appointments:
            mock_get_appointments.return_value = mock_appointments
            
            result = await client.check_for_appointment_creation(
                event_id='event_123',
                expected_subject='Test Meeting',
                start_datetime='2025-05-20T14:00:00Z',
                duration_minutes=60
            )
            
            assert result == 'event_123'
            mock_get_appointments.assert_called_once()
    
    async def test_check_for_appointment_creation_with_none_event_id_found(self):
        """Test searching by subject when event_id is None and appointment is found"""
        client = SalesforceApiClient()
        client._access_token = "mock_token" 
        client._instance_url = "https://mock-instance.salesforce.com"
        
        # Mock the get_scheduled_appointments_async method
        mock_appointments = [
            {
                'Id': 'event_456',
                'Subject': 'Team Standup',
                'StartDateTime': '2025-05-20T09:00:00+02:00',
                'EndDateTime': '2025-05-20T09:30:00+02:00'
            }
        ]
        
        with patch.object(client, 'get_scheduled_appointments_async', new_callable=AsyncMock) as mock_get_appointments:
            mock_get_appointments.return_value = mock_appointments
            
            result = await client.check_for_appointment_creation(
                event_id=None,
                expected_subject='Team Standup',
                start_datetime='2025-05-20T09:00:00Z',
                duration_minutes=30
            )
            
            assert result == 'event_456'
            mock_get_appointments.assert_called_once()
    
    async def test_check_for_appointment_creation_with_none_event_id_not_found(self):
        """Test searching by subject when event_id is None and appointment is not found"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        # Mock the get_scheduled_appointments_async method with different appointment
        mock_appointments = [
            {
                'Id': 'event_789',
                'Subject': 'Different Meeting',
                'StartDateTime': '2025-05-20T10:00:00+02:00',
                'EndDateTime': '2025-05-20T11:00:00+02:00'
            }
        ]
        
        with patch.object(client, 'get_scheduled_appointments_async', new_callable=AsyncMock) as mock_get_appointments:
            mock_get_appointments.return_value = mock_appointments
            
            result = await client.check_for_appointment_creation(
                event_id=None,
                expected_subject='Expected Meeting',
                start_datetime='2025-05-20T10:00:00Z',
                duration_minutes=60
            )
            
            assert result is None
            mock_get_appointments.assert_called_once()
    
    async def test_check_for_appointment_creation_appointment_not_found(self):
        """Test when appointment is not found with valid event_id"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        # Mock the get_scheduled_appointments_async method with different appointment
        mock_appointments = [
            {
                'Id': 'different_event',
                'Subject': 'Different Subject',
                'StartDateTime': '2025-05-20T14:00:00+02:00',
                'EndDateTime': '2025-05-20T15:00:00+02:00'
            }
        ]
        
        with patch.object(client, 'get_scheduled_appointments_async', new_callable=AsyncMock) as mock_get_appointments:
            mock_get_appointments.return_value = mock_appointments
            
            result = await client.check_for_appointment_creation(
                event_id='event_123',
                expected_subject='Test Meeting',
                start_datetime='2025-05-20T14:00:00Z',
                duration_minutes=60
            )
            
            assert result is None
            mock_get_appointments.assert_called_once()
    
    async def test_check_for_appointment_creation_empty_appointments(self):
        """Test when get_scheduled_appointments_async returns empty list"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        with patch.object(client, 'get_scheduled_appointments_async', new_callable=AsyncMock) as mock_get_appointments:
            mock_get_appointments.return_value = []
            
            result = await client.check_for_appointment_creation(
                event_id='event_123',
                expected_subject='Test Meeting',
                start_datetime='2025-05-20T14:00:00Z',
                duration_minutes=60
            )
            
            assert result is None
            mock_get_appointments.assert_called_once()
    
    async def test_check_for_appointment_creation_invalid_datetime(self):
        """Test with invalid start_datetime format"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        result = await client.check_for_appointment_creation(
            event_id='event_123',
            expected_subject='Test Meeting',
            start_datetime='invalid-datetime-format',
            duration_minutes=60
        )
        
        assert result is None
    
    async def test_check_for_appointment_creation_api_error(self):
        """Test when get_scheduled_appointments_async returns None (API error)"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        with patch.object(client, 'get_scheduled_appointments_async', new_callable=AsyncMock) as mock_get_appointments:
            mock_get_appointments.return_value = None
            
            result = await client.check_for_appointment_creation(
                event_id='event_123',
                expected_subject='Test Meeting',
                start_datetime='2025-05-20T14:00:00Z',
                duration_minutes=60
            )
            
            assert result is None
            mock_get_appointments.assert_called_once()
    
    async def test_check_for_appointment_creation_exception_handling(self):
        """Test exception handling in check_for_appointment_creation"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        with patch.object(client, 'get_scheduled_appointments_async', new_callable=AsyncMock) as mock_get_appointments:
            mock_get_appointments.side_effect = Exception("API connection error")
            
            result = await client.check_for_appointment_creation(
                event_id='event_123',
                expected_subject='Test Meeting',
                start_datetime='2025-05-20T14:00:00Z',
                duration_minutes=60
            )
            
            assert result is None
            mock_get_appointments.assert_called_once()
    
    async def test_check_for_appointment_creation_subject_mismatch(self):
        """Test when event_id matches but subject doesn't match"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        # Mock appointment with correct ID but wrong subject
        mock_appointments = [
            {
                'Id': 'event_123',
                'Subject': 'Wrong Subject',
                'StartDateTime': '2025-05-20T14:00:00+02:00',
                'EndDateTime': '2025-05-20T15:00:00+02:00'
            }
        ]
        
        with patch.object(client, 'get_scheduled_appointments_async', new_callable=AsyncMock) as mock_get_appointments:
            mock_get_appointments.return_value = mock_appointments
            
            result = await client.check_for_appointment_creation(
                event_id='event_123',
                expected_subject='Expected Subject',
                start_datetime='2025-05-20T14:00:00Z',
                duration_minutes=60
            )
            
            assert result is None
            mock_get_appointments.assert_called_once()
    
    async def test_check_for_appointment_creation_multiple_appointments_found(self):
        """Test when multiple appointments match the criteria"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        # Mock multiple appointments with same subject
        mock_appointments = [
            {
                'Id': 'event_111',
                'Subject': 'Daily Standup',
                'StartDateTime': '2025-05-20T09:00:00+02:00',
                'EndDateTime': '2025-05-20T09:30:00+02:00'
            },
            {
                'Id': 'event_222', 
                'Subject': 'Daily Standup',
                'StartDateTime': '2025-05-20T09:15:00+02:00',
                'EndDateTime': '2025-05-20T09:45:00+02:00'
            }
        ]
        
        with patch.object(client, 'get_scheduled_appointments_async', new_callable=AsyncMock) as mock_get_appointments:
            mock_get_appointments.return_value = mock_appointments
            
            # Test with event_id=None - should return first match
            result = await client.check_for_appointment_creation(
                event_id=None,
                expected_subject='Daily Standup',
                start_datetime='2025-05-20T09:00:00Z',
                duration_minutes=30
            )
            
            # Should return the first matching appointment ID
            assert result == 'event_111'
            mock_get_appointments.assert_called_once()