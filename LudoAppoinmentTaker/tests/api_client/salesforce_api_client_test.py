import pytest
import asyncio
import os
import logging
from datetime import datetime, timedelta
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

@pytest.mark.asyncio
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

@pytest.mark.asyncio
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

@pytest.mark.asyncio
async def test_schedule_new_appointment_async(salesforce_api_client: SalesforceApiClientInterface):
    """Test scheduling a new appointment"""
    now = datetime.now()
    start_datetime = now # Today, now + timedelta(days=1)  # Tomorrow
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
    
    # Log the created event ID
    logging.info(f"Created test appointment with ID: {event_id}")

@pytest.mark.asyncio
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

@pytest.mark.asyncio
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