import random
import datetime
import json # Added for pretty printing schema
from salesforce_api_client import SalesforceApiClient

# --- Action Handler Functions ---
def handle_create_event(client: SalesforceApiClient):
    print("\n--- Create New Event ---")
    subject = input("Enter event subject: ")
    start_date_str = input("Enter start date (YYYY-MM-DD): ")
    start_time_str = input("Enter start time (HH:MM in 24h format, UTC): ")
    try:
        duration_minutes = int(input("Enter duration in minutes (default 60): ") or 60)
    except ValueError:
        print("Invalid duration, using 60 minutes.")
        duration_minutes = 60
    
    description = input("Enter event description (optional): ")
    location = input("Enter event location (optional): ")
    # For demo, using a fixed owner_id and what_id. You might want to prompt for these.
    owner_id = '005Aa00000K990ZIAR' # Example Owner ID
    what_id = '006Aa00000Ii3XoIAJ'  # Example What ID (e.g., an Account or Opportunity)

    try:
        start_datetime_dt = datetime.datetime.strptime(f"{start_date_str}T{start_time_str}:00", "%Y-%m-%dT%H:%M:%S")
        # Ensure the datetime is timezone-aware (UTC)
        start_datetime_dt = start_datetime_dt.replace(tzinfo=datetime.timezone.utc)
        start_datetime_iso = start_datetime_dt.isoformat().replace('+00:00', 'Z')
    except ValueError:
        print("Invalid date/time format. Please use YYYY-MM-DD and HH:MM.")
        return

    event_id = client.create_event(
        subject=subject,
        description=description,
        start_datetime=start_datetime_iso,
        duration_minutes=duration_minutes,
        location=location,
        owner_id=owner_id,
        what_id=what_id
    )
    if event_id:
        print(f"Event created successfully with ID: {event_id}")
    else:
        print("Failed to create event.")

def handle_get_events(client: SalesforceApiClient):
    print("\n--- Get Events for a Period ---")
    start_date_str = input("Enter start date for period (YYYY-MM-DD, UTC): ")
    end_date_str = input("Enter end date for period (YYYY-MM-DD, UTC): ")
    owner_id_filter = input("Enter Owner ID to filter by (optional, e.g., 005Aa00000K990ZIAR): ") or None

    try:
        # Ensure the datetime is timezone-aware (UTC) at the beginning of the day
        start_dt = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
        start_datetime_iso = start_dt.isoformat().replace('+00:00', 'Z')
        # Ensure the datetime is timezone-aware (UTC) at the end of the day
        end_dt = datetime.datetime.strptime(end_date_str + "T23:59:59", "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
        end_datetime_iso = end_dt.isoformat().replace('+00:00', 'Z')
    except ValueError:
        print("Invalid date format. Please use YYYY-MM-DD.")
        return

    print(f"\nGetting events from {start_datetime_iso} to {end_datetime_iso}...")
    events = client.get_events(
        start_datetime=start_datetime_iso,
        end_datetime=end_datetime_iso,
        owner_id=owner_id_filter
    )
    
    if events:
        print(f"=> {len(events)} events found:")
        for event in events:
            start = datetime.datetime.fromisoformat(event['StartDateTime'].replace('Z', '+00:00'))
            end = datetime.datetime.fromisoformat(event['EndDateTime'].replace('Z', '+00:00'))
            date_str = start.strftime('%d/%m/%Y')
            start_time_str = start.strftime('%Hh%M')
            end_time_str = end.strftime('%Hh%M')
            print(f'  - On {date_str}, from {start_time_str} to {end_time_str}: "{event.get("Subject", "N/A")}". Description: {event.get("Description", "N/A")}')
    elif events == []: # Explicitly check for empty list vs None (error)
        print("No events found for the specified period.")
    else:
        print("Error occurred while retrieving events or no events found.")

def handle_get_person_by_phone(client: SalesforceApiClient):
    print("\n--- Get Person by Phone Number ---")
    phone_to_search = input("Enter phone number to search (e.g., +15551234567): ")
    if not phone_to_search:
        print("Phone number cannot be empty.")
        return
    person_info = client.get_person_by_phone(phone_to_search)

    if person_info:
        print(f"Found person of type: {person_info['type']}")
        person_data = person_info['data']
        owner_detail = person_data.get('Owner', {})
        owner_name = owner_detail.get('Name', 'N/A') if isinstance(owner_detail, dict) else 'N/A'
        
        print(f"  ID: {person_data.get('Id')}")
        print(f"  Name: {person_data.get('FirstName', '')} {person_data.get('LastName', '')}")
        print(f"  Email: {person_data.get('Email')}")
        print(f"  Phone: {person_data.get('Phone')}")
        print(f"  Mobile: {person_data.get('MobilePhone')}")
        print(f"  Owner: {owner_name}")

        if person_info['type'] == 'Contact':
            account_detail = person_data.get('Account', {})
            account_name = account_detail.get('Name', 'N/A') if isinstance(account_detail, dict) else 'N/A'
            print(f"  Account: {account_name}")
        elif person_info['type'] == 'Lead':
            print(f"  Company: {person_data.get('Company')}")
            print(f"  Status: {person_data.get('Status')}")
    else:
        print(f"No person found with phone number: {phone_to_search}")

def handle_discover_database(client: SalesforceApiClient):
    print("\n--- Discover Database Schema ---")
    sobjects_input = input("Enter SObject names to describe (comma-separated, e.g., Account,Contact,Lead) or leave blank for a default list: ")
    
    default_sobjects = ['Account', 'Contact', 'Lead', 'Opportunity', 'Event', 'User']
    sobjects_to_describe = [s.strip() for s in sobjects_input.split(',') if s.strip()] if sobjects_input else default_sobjects

    if not sobjects_to_describe:
        print("No SObjects specified for discovery. Using default list.")
        sobjects_to_describe = default_sobjects

    print(f"\nDiscovering database schema for: {', '.join(sobjects_to_describe)}...")
    schema_data = client.discover_database(sobjects_to_describe=sobjects_to_describe)

    if schema_data:
        print("Schema discovered. Summary:")
        for sobject_name, data in schema_data.items():
            if 'fields' in data:
                print(f"  SObject: {sobject_name}")
                print(f"    Fields found: {len(data['fields'])}")
                if 'Id' in data['fields']:
                    id_field = data['fields']['Id']
                    print(f"      Id: {id_field.get('type')}, PK: {id_field.get('is_primary_key')}")
                common_name_field_key = next((key for key in ['Name', 'Subject'] if key in data['fields']), None)
                if common_name_field_key:
                     field_detail = data['fields'][common_name_field_key]
                     print(f"      {field_detail.get('label')}: {field_detail.get('type')}, Label: '{field_detail.get('label')}'")       
            elif 'error' in data:
                print(f"  SObject: {sobject_name} - Error: {data['error']}")
        
        save_schema = input("Save full schema to salesforce_schema.json? (yes/no): ").lower()
        if save_schema == 'yes':
            try:
                with open('salesforce_schema.json', 'w') as f:
                    json.dump(schema_data, f, indent=2)
                print("Full schema saved to salesforce_schema.json")
            except Exception as e:
                print(f"Error saving schema: {e}")
    else:
        print("Could not retrieve database schema.")

def handle_get_leads(client: SalesforceApiClient):
    print("\n--- Get Leads by Details ---")
    email = input("Enter email to search (optional): ") or None
    first_name = input("Enter first name (optional, best with last name): ") or None
    last_name = input("Enter last name (optional, best with first name): ") or None
    company = input("Enter company name (optional): ") or None

    if not any([email, first_name, last_name, company]):
        print("Please provide at least one search criterion for leads.")
        return

    leads = client.get_leads_by_details(email=email, first_name=first_name, last_name=last_name, company_name=company)
    if leads is not None:
        if leads:
            print(f"Found {len(leads)} Lead(s):")
            for lead in leads:
                print(f"  Lead ID: {lead.get('Id')}, Name: {lead.get('FirstName')} {lead.get('LastName')}, Company: {lead.get('Company')}, Status: {lead.get('Status')}")
        else:
            print("No Leads found matching criteria.")
    else:
        print("Error occurred while searching for Leads.")

def handle_get_opportunities_for_lead(client: SalesforceApiClient):
    print("\n--- Get Opportunities for Lead ---")
    lead_id = input("Enter Lead ID to find related Opportunities: ")
    if not lead_id:
        print("Lead ID cannot be empty.")
        return

    opportunities = client.get_opportunities_for_lead(lead_id=lead_id)
    if opportunities is not None:
        if opportunities:
            print(f"Found {len(opportunities)} Opportunity(s) related to Lead ID '{lead_id}':")
            for opp in opportunities:
                account_detail = opp.get('Account', {})
                account_name = account_detail.get('Name', 'N/A') if isinstance(account_detail, dict) else 'N/A'
                print(f"  Opp ID: {opp.get('Id')}, Name: {opp.get('Name')}, Stage: {opp.get('StageName')}, Account: {account_name}")
        else:
            print(f"No Opportunities found directly related to Lead ID '{lead_id}'.")
    else:
        print(f"Error occurred while searching for Opportunities for Lead ID '{lead_id}'.")

def main():
    print("Initializing Salesforce API Client...")
    api_client = SalesforceApiClient(
        client_id='3MVG9IKwJOi7clC2.8QIzh9BkM6NhU53bup6EUfFQiXJ01nh.l2YJKF5vbNWqPkFEdjgzAXIqK3U1p2WCBUD3',
        username='etienne.millerioux@studi.fr',
        private_key_file='server.key',
        is_sandbox=True
    )
    
    # The SalesforceApiClient's __init__ method calls authenticate().
    # We check if authentication was successful by inspecting _access_token.
    if not api_client._access_token: # Accessing a protected member for this check
         print("CRITICAL: Salesforce authentication failed during client initialization. Exiting.")
         print("Please check your credentials, private key, and Salesforce connected app settings.")
         return
    print("Salesforce client authenticated successfully.")

    actions = {
        "1": ("Create New Event", handle_create_event),
        "2": ("Get Events for a Period", handle_get_events),
        "3": ("Get Person by Phone Number", handle_get_person_by_phone),
        "4": ("Discover Database Schema", handle_discover_database),
        "5": ("Get Leads by Details", handle_get_leads),
        "6": ("Get Opportunities for a Lead", handle_get_opportunities_for_lead),
        "0": ("Exit", None)
    }

    while True:
        print("\n--- Salesforce API Client Actions ---")
        for key, (description, _) in actions.items():
            print(f"{key}: {description}")
        
        choice = input("Enter your choice: ")
        
        if choice == "0":
            print("Exiting.")
            break
        
        action_tuple = actions.get(choice)
        if action_tuple:
            _, handler_function = action_tuple
            if handler_function:
                try:
                    handler_function(api_client)
                except Exception as e:
                    print(f"An error occurred while executing action '{action_tuple[0]}': {e}")
                    # Optionally, add more detailed error logging or traceback here
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()
