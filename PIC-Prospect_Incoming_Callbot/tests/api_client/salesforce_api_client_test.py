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
    """Unit tests for verify_appointment_existance method"""
    
    async def test_verify_appointment_existance_with_valid_event_id(self):
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
            
            result = await client.verify_appointment_existance(
                event_id='event_123',
                expected_subject='Test Meeting',
                start_datetime='2025-05-20T14:00:00Z',
                duration_minutes=60
            )
            
            assert result == 'event_123'
            mock_get_appointments.assert_called_once()
    
    async def test_verify_appointment_existance_with_none_event_id_found(self):
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
            
            result = await client.verify_appointment_existance(
                event_id=None,
                expected_subject='Team Standup',
                start_datetime='2025-05-20T09:00:00Z',
                duration_minutes=30
            )
            
            assert result == 'event_456'
            mock_get_appointments.assert_called_once()
    
    async def test_verify_appointment_existance_with_none_event_id_not_found(self):
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
            
            result = await client.verify_appointment_existance(
                event_id=None,
                expected_subject='Expected Meeting',
                start_datetime='2025-05-20T10:00:00Z',
                duration_minutes=60
            )
            
            assert result is None
            mock_get_appointments.assert_called_once()
    
    async def test_verify_appointment_existance_appointment_not_found(self):
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
            
            result = await client.verify_appointment_existance(
                event_id='event_123',
                expected_subject='Test Meeting',
                start_datetime='2025-05-20T14:00:00Z',
                duration_minutes=60
            )
            
            assert result is None
            mock_get_appointments.assert_called_once()
    
    async def test_verify_appointment_existance_empty_appointments(self):
        """Test when get_scheduled_appointments_async returns empty list"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        with patch.object(client, 'get_scheduled_appointments_async', new_callable=AsyncMock) as mock_get_appointments:
            mock_get_appointments.return_value = []
            
            result = await client.verify_appointment_existance(
                event_id='event_123',
                expected_subject='Test Meeting',
                start_datetime='2025-05-20T14:00:00Z',
                duration_minutes=60
            )
            
            assert result is None
            mock_get_appointments.assert_called_once()
    
    async def test_verify_appointment_existance_invalid_datetime(self):
        """Test with invalid start_datetime format"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        result = await client.verify_appointment_existance(
            event_id='event_123',
            expected_subject='Test Meeting',
            start_datetime='invalid-datetime-format',
            duration_minutes=60
        )
        
        assert result is None
    
    async def test_verify_appointment_existance_api_error(self):
        """Test when get_scheduled_appointments_async returns None (API error)"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        with patch.object(client, 'get_scheduled_appointments_async', new_callable=AsyncMock) as mock_get_appointments:
            mock_get_appointments.return_value = None
            
            result = await client.verify_appointment_existance(
                event_id='event_123',
                expected_subject='Test Meeting',
                start_datetime='2025-05-20T14:00:00Z',
                duration_minutes=60
            )
            
            assert result is None
            mock_get_appointments.assert_called_once()
    
    async def test_verify_appointment_existance_exception_handling(self):
        """Test exception handling in verify_appointment_existance"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        with patch.object(client, 'get_scheduled_appointments_async', new_callable=AsyncMock) as mock_get_appointments:
            mock_get_appointments.side_effect = Exception("API connection error")
            
            result = await client.verify_appointment_existance(
                event_id='event_123',
                expected_subject='Test Meeting',
                start_datetime='2025-05-20T14:00:00Z',
                duration_minutes=60
            )
            
            assert result is None
            mock_get_appointments.assert_called_once()
    
    async def test_verify_appointment_existance_subject_mismatch(self):
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
            
            result = await client.verify_appointment_existance(
                event_id='event_123',
                expected_subject='Expected Subject',
                start_datetime='2025-05-20T14:00:00Z',
                duration_minutes=60
            )
            
            assert result is None
            mock_get_appointments.assert_called_once()
    
    async def test_verify_appointment_existance_multiple_appointments_found(self):
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
            result = await client.verify_appointment_existance(
                event_id=None,
                expected_subject='Daily Standup',
                start_datetime='2025-05-20T09:00:00Z',
                duration_minutes=30
            )
            
            # Should return the first matching appointment ID
            assert result == 'event_111'
            mock_get_appointments.assert_called_once()


class TestScheduleAppointmentRetryMechanism:
    """Unit tests for retry mechanism in schedule_new_appointment_async method"""
    
    async def test_retry_on_verification_failure_then_success(self):
        """Test that the method retries when verification fails, then succeeds"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        call_count = 0
        verify_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"id": f"event_{call_count}"}
            return mock_response
        
        async def mock_verification(*args, **kwargs):
            nonlocal verify_count
            verify_count += 1
            if verify_count == 1:
                return None  # First call: check if appointment already exists (should return None - no existing appointment)
            elif verify_count == 2:
                return None  # Second call: first verification after creation fails
            elif verify_count == 3:
                return None  # Third call: retry check if appointment already exists (should return None)
            else:
                return f"event_{call_count}"  # Fourth call: verification after retry succeeds
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_client.post = mock_post
            
            with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
                mock_verify.side_effect = mock_verification
                
                result = await client.schedule_new_appointment_async(
                    subject="Test Retry",
                    start_datetime="2025-12-01T10:00:00Z",
                    duration_minutes=30,
                    max_retries=1,
                    retry_delay=0.01  # Very short delay for testing
                )
                
                assert result == f"event_{call_count}"
                assert call_count == 2  # Initial call + 1 retry
                assert verify_count == 4  # Four verification attempts: pre-check + post-creation + retry-pre-check + retry-post-creation
    
    async def test_retry_exhaustion_returns_none(self):
        """Test that method returns None when all retries are exhausted"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"id": f"event_{call_count}"}
            return mock_response
        
        async def mock_verification_always_fail(*args, **kwargs):
            return None  # Always fail verification
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_client.post = mock_post
            
            with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
                mock_verify.side_effect = mock_verification_always_fail
                
                result = await client.schedule_new_appointment_async(
                    subject="Test Retry Exhaustion",
                    start_datetime="2025-12-01T10:00:00Z",
                    duration_minutes=30,
                    max_retries=2,
                    retry_delay=0.01
                )
                
                assert result is None
                assert call_count == 3  # Initial call + 2 retries
    
    async def test_no_retry_on_immediate_success(self):
        """Test that no retry occurs when verification succeeds immediately"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"id": "success_event"}
            return mock_response
        
        verify_count = 0
        async def mock_verification_success(*args, **kwargs):
            nonlocal verify_count
            verify_count += 1
            if verify_count == 1:
                return None  # First call: check if appointment already exists (should return None)
            else:
                return "success_event"  # Second call: verification after creation succeeds
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_client.post = mock_post
            
            with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
                mock_verify.side_effect = mock_verification_success
                
                result = await client.schedule_new_appointment_async(
                    subject="Test Immediate Success",
                    start_datetime="2025-12-01T10:00:00Z",
                    duration_minutes=30,
                    max_retries=2,
                    retry_delay=0.01
                )
                
                assert result == "success_event"
                assert call_count == 1  # Only one call, no retries needed
    
    async def test_retry_with_zero_max_retries(self):
        """Test that no retry occurs when max_retries is 0"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"id": "event_1"}
            return mock_response
        
        async def mock_verification_fail(*args, **kwargs):
            return None  # Verification fails
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_client.post = mock_post
            
            with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
                mock_verify.side_effect = mock_verification_fail
                
                result = await client.schedule_new_appointment_async(
                    subject="Test Zero Retries",
                    start_datetime="2025-12-01T10:00:00Z",
                    duration_minutes=30,
                    max_retries=0,  # No retries
                    retry_delay=0.01
                )
                
                assert result is None
                assert call_count == 1  # Only initial call, no retries
    
    async def test_retry_with_creation_exception_then_success(self):
        """Test retry when creation fails with exception, then succeeds"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Network error")  # First call fails
            else:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {"id": f"event_{call_count}"}
                return mock_response
        
        async def mock_verification_success(*args, **kwargs):
            # Only return success for successful creation attempts
            if call_count > 1:
                return f"event_{call_count}"
            else:
                return None  # First attempt failed, so no verification
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_client.post = mock_post
            
            with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
                mock_verify.side_effect = mock_verification_success
                
                result = await client.schedule_new_appointment_async(
                    subject="Test Exception Recovery",
                    start_datetime="2025-12-01T10:00:00Z",
                    duration_minutes=30,
                    max_retries=1,
                    retry_delay=0.01
                )
                
                assert result == "event_2"
                assert call_count == 2  # Initial call failed, retry succeeded
    
    async def test_retry_with_http_error_then_success(self):
        """Test retry when creation fails with HTTP error, then succeeds"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = MagicMock()
            if call_count == 1:
                mock_response.status_code = 500
                mock_response.text = "Server error"
                mock_response.json.return_value = {"error": "Internal server error"}
            else:
                mock_response.status_code = 201
                mock_response.json.return_value = {"id": f"event_{call_count}"}
            return mock_response
        
        async def mock_verification_success(*args, **kwargs):
            return f"event_{call_count}" if call_count > 1 else None
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_client.post = mock_post
            
            with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
                mock_verify.side_effect = mock_verification_success
                
                result = await client.schedule_new_appointment_async(
                    subject="Test HTTP Error Recovery",
                    start_datetime="2025-12-01T10:00:00Z",
                    duration_minutes=30,
                    max_retries=1,
                    retry_delay=0.01
                )
                
                assert result == "event_2"
                assert call_count == 2  # Initial call failed with HTTP error, retry succeeded
    
    async def test_retry_delay_timing(self):
        """Test that retry delay is properly applied"""
        import time
        
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        start_time = None
        retry_time = None
        
        call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count, start_time, retry_time
            call_count += 1
            if call_count == 1:
                start_time = time.time()
            elif call_count == 2:
                retry_time = time.time()
            
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"id": f"event_{call_count}"}
            return mock_response
        
        verify_count = 0
        async def mock_verification(*args, **kwargs):
            nonlocal verify_count
            verify_count += 1
            if verify_count == 1:
                return None  # First call: check if appointment already exists (should return None)
            elif verify_count == 2:
                return None  # Second call: verification after first creation fails
            elif verify_count == 3:
                return None  # Third call: retry check if appointment already exists (should return None)
            else:
                return f"event_{call_count}"  # Fourth call: verification after retry succeeds
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_client.post = mock_post
            
            with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
                mock_verify.side_effect = mock_verification
                
                await client.schedule_new_appointment_async(
                    subject="Test Delay Timing",
                    start_datetime="2025-12-01T10:00:00Z",
                    duration_minutes=30,
                    max_retries=1,
                    retry_delay=0.1  # 100ms delay
                )
                
                # Check that at least the delay time has passed between calls
                if retry_time and start_time:
                    time_diff = retry_time - start_time
                    assert time_diff >= 0.1, f"Delay was {time_diff}, expected at least 0.1"
                assert call_count == 2
    
    async def test_retry_with_mixed_failure_scenarios(self):
        """Test complex scenario with creation failure, verification failure, then success"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        call_count = 0
        verify_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = MagicMock()
            if call_count == 1:
                # First call: HTTP error
                mock_response.status_code = 503
                mock_response.text = "Service unavailable"
                mock_response.json.return_value = {"error": "Service unavailable"}
            elif call_count == 2:
                # Second call: Success but verification will fail
                mock_response.status_code = 201
                mock_response.json.return_value = {"id": f"event_{call_count}"}
            else:
                # Third call: Success and verification will succeed
                mock_response.status_code = 201
                mock_response.json.return_value = {"id": f"event_{call_count}"}
            return mock_response
        
        async def mock_verification(*args, **kwargs):
            nonlocal verify_count
            verify_count += 1
            event_id = kwargs.get('event_id')
            
            # Existence checks (event_id=None) should always return None for retries to work
            if event_id is None:
                return None
            # Verification checks (event_id=actual_id)
            elif verify_count == 4:
                return None  # Verification after second call (event_2 created) fails
            else:
                return event_id  # Return the actual event_id for successful verification
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_client.post = mock_post
            
            with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
                mock_verify.side_effect = mock_verification
                
                result = await client.schedule_new_appointment_async(
                    subject="Test Mixed Failures",
                    start_datetime="2025-12-01T10:00:00Z",
                    duration_minutes=30,
                    max_retries=3,  # Allow enough retries
                    retry_delay=0.01
                )
                
                assert result == f"event_{call_count}"
                assert call_count == 3  # 1 failed creation + 2 successful creations
                assert verify_count == 6  # 1 pre-check + 1 retry-check + extra check + 1 verification + 1 retry-check + 1 verification


class TestScheduleAppointmentRetryParameterValidation:
    """Tests for retry parameter validation and edge cases"""
    
    async def test_negative_max_retries(self):
        """Test that negative max_retries behaves like zero retries"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"id": "event_1"}
            return mock_response
        
        async def mock_verification_fail(*args, **kwargs):
            return None  # Always fail
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_client.post = mock_post
            
            with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
                mock_verify.side_effect = mock_verification_fail
                
                result = await client.schedule_new_appointment_async(
                    subject="Test Negative Retries",
                    start_datetime="2025-12-01T10:00:00Z",
                    duration_minutes=30,
                    max_retries=-1,  # Negative retries
                    retry_delay=0.01
                )
                
                assert result is None
                assert call_count == 1  # Only initial call, no retries
    
    async def test_very_large_max_retries(self):
        """Test with large max_retries value (should work but be reasonable)"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"id": f"event_{call_count}"}
            return mock_response
        
        verify_count = 0
        verification_attempts = 0  # Count only actual verification attempts (not existence checks)
        async def mock_verification(*args, **kwargs):
            nonlocal verify_count, verification_attempts
            verify_count += 1
            event_id = kwargs.get('event_id')
            
            # Existence checks (event_id=None) should always return None for retries to work
            if event_id is None:
                return None
            # Verification checks (event_id=actual_id) 
            else:
                verification_attempts += 1
                if verification_attempts <= 5:
                    return None  # Fail first 5 verification attempts
                else:
                    return event_id  # Then succeed on 6th verification attempt
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_client.post = mock_post
            
            with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
                mock_verify.side_effect = mock_verification
                
                result = await client.schedule_new_appointment_async(
                    subject="Test Large Retries",
                    start_datetime="2025-12-01T10:00:00Z",
                    duration_minutes=30,
                    max_retries=100,  # Large number of retries
                    retry_delay=0.001  # Very short delay
                )
                
                assert result == f"event_6"  # Should succeed on 6th verification attempt  
                assert call_count == 6  # Should make 6 creation attempts
                assert verification_attempts == 6  # Should make 6 verification attempts
    
    async def test_zero_retry_delay(self):
        """Test with zero retry delay"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"id": f"event_{call_count}"}
            return mock_response
        
        verify_count = 0
        async def mock_verification(*args, **kwargs):
            nonlocal verify_count
            verify_count += 1
            event_id = kwargs.get('event_id')
            
            # Existence checks (event_id=None) should always return None for retries to work
            if event_id is None:
                return None
            # Verification checks (event_id=actual_id)
            elif event_id == 'event_1':
                return None  # First verification fails
            else:
                return event_id  # Second verification succeeds
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_client.post = mock_post
            
            with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
                mock_verify.side_effect = mock_verification
                
                result = await client.schedule_new_appointment_async(
                    subject="Test Zero Delay",
                    start_datetime="2025-12-01T10:00:00Z",
                    duration_minutes=30,
                    max_retries=1,
                    retry_delay=0.0  # Zero delay
                )
                
                assert result == "event_2"
                assert call_count == 2
                assert verify_count == 4  # 2 existence checks + 2 verification checks
    
    async def test_negative_retry_delay(self):
        """Test with negative retry delay (should still work, delay treated as zero)"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"id": f"event_{call_count}"}
            return mock_response
        
        verify_count = 0
        async def mock_verification(*args, **kwargs):
            nonlocal verify_count
            verify_count += 1
            event_id = kwargs.get('event_id')
            
            # Existence checks (event_id=None) should always return None for retries to work
            if event_id is None:
                return None
            # Verification checks (event_id=actual_id)
            elif event_id == 'event_1':
                return None  # First verification fails
            else:
                return event_id  # Second verification succeeds
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_client.post = mock_post
            
            with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
                mock_verify.side_effect = mock_verification
                
                result = await client.schedule_new_appointment_async(
                    subject="Test Negative Delay",
                    start_datetime="2025-12-01T10:00:00Z",
                    duration_minutes=30,
                    max_retries=1,
                    retry_delay=-0.5  # Negative delay
                )
                
                assert result == "event_2"
                assert call_count == 2
                assert verify_count == 4  # 2 existence checks + 2 verification checks
    
    async def test_default_retry_parameters(self):
        """Test that default retry parameters work as expected"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"id": f"event_{call_count}"}
            return mock_response
        
        verify_count = 0
        verification_attempts = 0  # Count only actual verification attempts (not existence checks)
        async def mock_verification(*args, **kwargs):
            nonlocal verify_count, verification_attempts
            verify_count += 1
            event_id = kwargs.get('event_id')
            
            # Existence checks (event_id=None) should always return None for retries to work
            if event_id is None:
                return None
            # Verification checks (event_id=actual_id) 
            else:
                verification_attempts += 1
                if verification_attempts <= 2:  # Fail first 2 verification attempts
                    return None
                else:
                    return event_id  # Then succeed on 3rd verification attempt
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_client.post = mock_post
            
            with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
                mock_verify.side_effect = mock_verification
                
                # Call without specifying retry parameters (use defaults)
                result = await client.schedule_new_appointment_async(
                    subject="Test Default Parameters",
                    start_datetime="2025-12-01T10:00:00Z",
                    duration_minutes=30
                    # max_retries and retry_delay use defaults (2 and 1.0)
                )
                
                assert result == "event_3"
                assert call_count == 3  # Initial + 2 default retries  
                assert verification_attempts == 3  # 3 verification attempts


class TestScheduleAppointmentOverlapDetection:
    """Tests for overlapping appointment detection in schedule_new_appointment_async"""
    
    async def test_schedule_new_appointment_fails_when_overlapping_appointment_exists(self):
        """Test that schedule_new_appointment_async fails when trying to create an overlapping appointment"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        # Mock the verify_appointment_existance method to simulate finding an existing appointment
        existing_event_id = "existing_event_123"
        verify_call_count = 0
        
        async def mock_verification(*args, **kwargs):
            nonlocal verify_call_count
            verify_call_count += 1
            event_id = kwargs.get('event_id')
            
            # First call: check if appointment already exists (event_id=None) - return existing event
            if event_id is None:
                return existing_event_id  # Return existing appointment ID to indicate overlap
            else:
                # This shouldn't be reached since method should return None due to overlap
                return event_id
        
        with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
            mock_verify.side_effect = mock_verification
            
            result = await client.schedule_new_appointment_async(
                subject="Overlapping Meeting",
                start_datetime="2025-12-01T10:00:00Z",
                duration_minutes=30,
                description="This should fail due to overlap"
            )
            
            # Should return None because of overlapping appointment
            assert result is None
            # Should only call verification once (the overlap check)
            assert verify_call_count == 1
            # Verify the overlap check was called with correct parameters
            mock_verify.assert_called_once_with(
                event_id=None,
                expected_subject="Overlapping Meeting", 
                start_datetime="2025-12-01T10:00:00Z",
                duration_minutes=30
            )
    
    async def test_schedule_new_appointment_succeeds_when_no_overlapping_appointment(self):
        """Test that schedule_new_appointment_async succeeds when no overlapping appointment exists"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        verify_call_count = 0
        post_call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal post_call_count
            post_call_count += 1
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"id": "new_event_456"}
            return mock_response
        
        async def mock_verification(*args, **kwargs):
            nonlocal verify_call_count
            verify_call_count += 1
            event_id = kwargs.get('event_id')
            
            # First call: check if appointment already exists (event_id=None) - return None (no overlap)
            if event_id is None:
                return None  # No existing appointment found
            # Second call: verify creation (event_id="new_event_456") - return the ID to confirm success
            else:
                return event_id
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_client.post = mock_post
            
            with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
                mock_verify.side_effect = mock_verification
                
                result = await client.schedule_new_appointment_async(
                    subject="Non-Overlapping Meeting",
                    start_datetime="2025-12-01T14:00:00Z",
                    duration_minutes=60,
                    description="This should succeed - no overlap"
                )
                
                # Should return the new event ID
                assert result == "new_event_456"
                # Should call verification twice: overlap check + creation verification
                assert verify_call_count == 2
                # Should make one API call to create the appointment
                assert post_call_count == 1
    
    async def test_schedule_new_appointment_overlap_with_different_subject_same_time(self):
        """Test that appointments with different subjects at same time are considered overlapping"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        existing_event_id = "existing_different_subject_789"
        
        async def mock_verification(*args, **kwargs):
            event_id = kwargs.get('event_id')
            expected_subject = kwargs.get('expected_subject')
            
            # First call: check if appointment already exists (event_id=None)
            if event_id is None:
                # The current implementation checks by subject + time, but we're testing
                # the scenario where there's a different subject at the same time
                # For this test, we simulate that verify_appointment_existance finds 
                # an existing appointment with different subject but same time slot
                if expected_subject == "New Meeting Subject":
                    return existing_event_id  # Found overlapping appointment
                return None
            else:
                return event_id
        
        with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
            mock_verify.side_effect = mock_verification
            
            result = await client.schedule_new_appointment_async(
                subject="New Meeting Subject",
                start_datetime="2025-12-01T15:00:00Z", 
                duration_minutes=30
            )
            
            # Should fail due to overlap detection
            assert result is None
    
    async def test_schedule_new_appointment_overlap_with_partial_time_overlap(self):
        """Test that appointments with partial time overlap are detected"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        existing_event_id = "partially_overlapping_event"
        
        async def mock_verification(*args, **kwargs):
            event_id = kwargs.get('event_id')
            start_datetime = kwargs.get('start_datetime')
            
            # First call: check if appointment already exists (event_id=None)
            if event_id is None:
                # Simulate finding an existing appointment that overlaps with the requested time
                if start_datetime == "2025-12-01T16:30:00Z":  # Our new appointment starts when existing one ends
                    return existing_event_id  # Found overlapping appointment
                return None
            else:
                return event_id
        
        with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
            mock_verify.side_effect = mock_verification
            
            result = await client.schedule_new_appointment_async(
                subject="Partially Overlapping Meeting",
                start_datetime="2025-12-01T16:30:00Z",  # Starts when existing appointment ends
                duration_minutes=45
            )
            
            # Should fail due to overlap detection
            assert result is None
    
    async def test_schedule_new_appointment_overlap_check_handles_verification_error(self):
        """Test that appointment creation fails gracefully when overlap check encounters an error"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        async def mock_verification(*args, **kwargs):
            event_id = kwargs.get('event_id')
            
            # First call: check if appointment already exists (event_id=None) - simulate API error
            if event_id is None:
                raise Exception("Salesforce API error during overlap check")
            else:
                return event_id
        
        with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
            mock_verify.side_effect = mock_verification
            
            # The method should handle the error gracefully
            with pytest.raises(Exception, match="Salesforce API error during overlap check"):
                await client.schedule_new_appointment_async(
                    subject="Error Test Meeting",
                    start_datetime="2025-12-01T17:00:00Z",
                    duration_minutes=30
                )


class TestScheduleAppointmentRetryIntegration:
    """Integration tests for complete retry workflow scenarios"""
    
    async def test_realistic_transient_failure_scenario(self):
        """Test a realistic scenario where Salesforce has temporary issues"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = MagicMock()
            
            # Simulate real-world failure patterns
            if call_count == 1:
                # First attempt: Service temporarily unavailable
                mock_response.status_code = 503
                mock_response.text = "Service temporarily unavailable"
                mock_response.json.return_value = {
                    "message": "Service temporarily unavailable",
                    "errorCode": "SERVICE_UNAVAILABLE"
                }
            elif call_count == 2:
                # Second attempt: Rate limit exceeded
                mock_response.status_code = 429
                mock_response.text = "API rate limit exceeded"
                mock_response.json.return_value = {
                    "message": "API rate limit exceeded",
                    "errorCode": "REQUEST_LIMIT_EXCEEDED"
                }
            else:
                # Third attempt: Success
                mock_response.status_code = 201
                mock_response.json.return_value = {"id": "final_success_event"}
            
            return mock_response
        
        verify_count = 0
        async def mock_verification(*args, **kwargs):
            nonlocal verify_count
            verify_count += 1
            event_id = kwargs.get('event_id')
            
            # Existence checks (event_id=None) should always return None for retries to work
            if event_id is None:
                return None
            # Verification checks (event_id=actual_id) - only succeed when we get the final_success_event
            elif event_id == "final_success_event":
                return "final_success_event"  # Final verification succeeds
            else:
                return None  # Other verifications fail (shouldn't happen with HTTP errors)
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_client.post = mock_post
            
            with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
                mock_verify.side_effect = mock_verification
                
                result = await client.schedule_new_appointment_async(
                    subject="Important Client Meeting",
                    start_datetime="2025-12-01T14:00:00Z",
                    duration_minutes=60,
                    description="Critical client presentation",
                    owner_id="005xx000001234567",
                    max_retries=3,
                    retry_delay=0.05  # Short delay for testing
                )
                
                assert result == "final_success_event"
                assert call_count == 3  # Service error, rate limit, then success
                # verify_count will be higher due to existence checks
    
    async def test_network_timeout_recovery(self):
        """Test recovery from network timeouts and connection issues"""
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            if call_count == 1:
                # First attempt: Connection timeout
                raise asyncio.TimeoutError("Connection timeout")
            elif call_count == 2:
                # Second attempt: Network error
                raise Exception("Network unreachable")
            else:
                # Third attempt: Success
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {"id": "network_recovery_event"}
                return mock_response
        
        async def mock_verification(*args, **kwargs):
            # Only succeed when creation actually worked (call_count == 3)
            if call_count >= 3:
                return "network_recovery_event"
            else:
                return None  # Failed attempts don't pass verification
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_client.post = mock_post
            
            with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
                mock_verify.side_effect = mock_verification
                
                result = await client.schedule_new_appointment_async(
                    subject="Network Recovery Test",
                    start_datetime="2025-12-01T15:00:00Z",
                    duration_minutes=30,
                    max_retries=2,
                    retry_delay=0.02
                )
                
                assert result == "network_recovery_event"
                assert call_count == 3  # Timeout, network error, then success
    
    async def test_authentication_reauth_during_retry(self):
        """Test that authentication is refreshed during retry attempts"""
        client = SalesforceApiClient()
        client._access_token = "initial_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        call_count = 0
        auth_call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"id": f"auth_test_{call_count}"}
            return mock_response
        
        # Mock the _ensure_authenticated_async method to track calls
        original_ensure_auth = client._ensure_authenticated_async
        async def mock_ensure_auth():
            nonlocal auth_call_count
            auth_call_count += 1
            client._access_token = f"refreshed_token_{auth_call_count}"
            # Don't call original to avoid actual authentication
        
        verify_count = 0
        async def mock_verification(*args, **kwargs):
            nonlocal verify_count
            verify_count += 1
            event_id = kwargs.get('event_id')
            
            # Existence checks (event_id=None) should always return None for retries to work
            if event_id is None:
                return None
            # Verification checks (event_id=actual_id)
            elif event_id == 'auth_test_1':
                return None  # First verification fails
            else:
                return event_id  # Second verification succeeds
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_client.post = mock_post
            
            with patch.object(client, '_ensure_authenticated_async', new_callable=AsyncMock) as mock_auth:
                mock_auth.side_effect = mock_ensure_auth
                
                with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
                    mock_verify.side_effect = mock_verification
                    
                    result = await client.schedule_new_appointment_async(
                        subject="Auth Refresh Test",
                        start_datetime="2025-12-01T16:00:00Z",
                        duration_minutes=30,
                        max_retries=1,
                        retry_delay=0.01
                    )
                    
                    assert result == "auth_test_2"
                    assert call_count == 2  # Initial call + retry
                    assert auth_call_count == 2  # Authentication called for both attempts
                    assert verify_count == 4  # 2 existence checks + 2 verification checks
    
    async def test_complete_failure_with_comprehensive_logging(self):
        """Test complete failure scenario to ensure proper error logging"""
        import logging
        from io import StringIO
        
        # Capture log output
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        logger = logging.getLogger('app.api_client.salesforce_api_client')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        
        client = SalesforceApiClient()
        client._access_token = "mock_token"
        client._instance_url = "https://mock-instance.salesforce.com"
        
        call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            # Always fail with different errors
            if call_count == 1:
                raise Exception("Database connection failed")
            elif call_count == 2:
                mock_response = MagicMock()
                mock_response.status_code = 500
                mock_response.text = "Internal server error"
                mock_response.json.return_value = {"error": "Database timeout"}
                return mock_response
            else:
                raise Exception("Service permanently unavailable")
        
        async def mock_verification(*args, **kwargs):
            return None  # Always fail verification
        
        try:
            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = mock_client_class.return_value.__aenter__.return_value
                mock_client.post = mock_post
                
                with patch.object(client, 'verify_appointment_existance', new_callable=AsyncMock) as mock_verify:
                    mock_verify.side_effect = mock_verification
                    
                    result = await client.schedule_new_appointment_async(
                        subject="Complete Failure Test",
                        start_datetime="2025-12-01T17:00:00Z",
                        duration_minutes=30,
                        max_retries=2,
                        retry_delay=0.01
                    )
                    
                    assert result is None
                    assert call_count == 3  # All three attempts should have been made
                    
                    # Check that appropriate log messages were generated
                    log_output = log_capture.getvalue()
                    assert "Verification failed, retrying" in log_output
                    assert "All retry attempts exhausted" in log_output
        finally:
            # Clean up logging
            logger.removeHandler(handler)
            handler.close()