import jwt
import os
import httpx
import urllib.parse
import logging
import time
import json
from datetime import datetime, timedelta, timezone
import pytz
import asyncio
import re
from time import tzname
from utils.envvar import EnvHelper
from api_client.salesforce_api_client_interface import SalesforceApiClientInterface

class SalesforceApiClient(SalesforceApiClientInterface):
    _client_id = '3MVG9IKwJOi7clC2.8QIzh9BkM6NhU53bup6EUfFQiXJ01nh.l2YJKF5vbNWqPkFEdjgzAXIqK3U1p2WCBUD3'
    _username = EnvHelper.get_salesforce_username()
    _password = EnvHelper.get_salesforce_password()
    _client_secret = EnvHelper.get_salesforce_client_secret()
    _private_key_file = 'salesforce_server_private.key'
    _is_sandbox = True

    def __init__(self, client_id: str = None, username: str = None, private_key_file: str = None, is_sandbox: bool = True):
        self.logger = logging.getLogger(__name__)
        self._client_id = client_id or self._client_id
        self._username = username or self._username
        self._private_key_file = private_key_file or self._private_key_file
        self._is_sandbox = is_sandbox or self._is_sandbox
        
        # API settings
        salesforce_domain = 'salesforce.com'
        self.subdomain = 'test' if is_sandbox else 'login'
        self._auth_url = f'https://{self.subdomain}.{salesforce_domain}/services/oauth2/token'
        self._version_api = 'v60.0'
        
        self._access_token = None
        self._instance_url = None
        self.authenticate() # Eager authentication on initialization
            
    def authenticate(self) -> bool:
        """Authenticate with Salesforce using JWT and return success status"""
        self.logger.info("Salesforce Authentication in progress...")
    
        # # Read private key
        # try:
        #     script_dir = os.path.dirname(os.path.abspath(__file__))
        #     key_path = os.path.join(script_dir, self._private_key_file)
        #     with open(key_path, 'r') as f:
        #         private_key = f.read()
        # except FileNotFoundError:
        #     self.logger.error(f"Error: Private key file '{self._private_key_file}' not found")
        #     self._access_token = None
        #     self._instance_url = None
        #     return False
        
        # # Create JWT payload
        # payload = {
        #     'iss': self._client_id,
        #     'sub': self._username,
        #     'aud': self._auth_url,
        #     'exp': int(time.time()) + 300  # 5 minutes expiration
        # }
        # # Encode JWT
        # jwt_token = jwt.encode(payload, private_key, algorithm='RS256')
        # # Prepare authentication request
        # params = {
        #     'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        #     'assertion': jwt_token
        # }

        params = {
            'grant_type': 'password',
            'client_id': self._client_id,
            'client_secret': self._client_secret,
            'username': self._username,
            'password': self._password
        }
        
        # Send authentication request
        with httpx.Client() as client:
            try:
                response = client.post(self._auth_url, data=params)
                response.raise_for_status()
                
                # Process response
                auth_data = response.json()
                self._access_token = auth_data.get('access_token')
                self._instance_url = auth_data.get('instance_url')
                
                if self._access_token and self._instance_url:
                    self.logger.info("Authentication successful.")
                    return True
                else:
                    error_msg = "Authentication completed but access_token or instance_url is missing."
                    if not self._access_token:
                        error_msg += " Access token is missing."
                    if not self._instance_url:
                        error_msg += " Instance URL is missing."
                    self.logger.info(error_msg)
                    self._access_token = None # Ensure clean state
                    self._instance_url = None
                    return False
                
            except httpx.HTTPStatusError as e:
                self.logger.info(f"Authentication HTTP error: {e.response.status_code} - {e.response.text}")
                self._access_token = None 
                self._instance_url = None
                return False
            except Exception as e:
                self.logger.info(f"Authentication error: {str(e)}")
                self._access_token = None 
                self._instance_url = None
                return False

    async def _ensure_authenticated_async(self):
        if not self._access_token or not self._instance_url:
            if not self.authenticate():
                raise Exception("Salesforce authentication failed. Cannot proceed with API call.")

    async def schedule_new_appointment_async(self, subject: str, start_datetime: str, duration_minutes: int = 30, description: str | None = None, 
                   location: str | None = None, owner_id: str | None = None, 
                   what_id: str | None = None, who_id: str | None = None,
                   max_retries: int = 2, retry_delay: float = 1.0) -> str | None:
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
            max_retries: Maximum number of retry attempts if verification fails (default: 3)
            retry_delay: Delay in seconds before recursive retry attempt (default: 1.0)
            
        Returns:
            The ID of the created event if successful, None otherwise
        """        
        await self._ensure_authenticated_async()
        if not subject or not start_datetime:
            self.logger.info("Error: Required event fields (subject, start_datetime) are missing")
            return None

        # Convert to UTC
        start_dt = self._get_french_datetime_from_str(start_datetime)
        if start_dt is None:
            self.logger.info("Error: Invalid start_datetime format")
            return None
        # TODO NOW: tmp to fix timezone issue in docker container
        french_now = datetime.now(pytz.timezone('Europe/Paris'))
        utc_offset_hours = (french_now.utcoffset().total_seconds() or 0) / 3600        
        if utc_offset_hours != 0:
            start_dt = start_dt - timedelta(hours=utc_offset_hours)
            self.logger.error(f"<<@>> UTC offset hours removed: {utc_offset_hours}")

        start_datetime_utc = self._to_utc_datetime(start_dt)
            
        if start_datetime_utc <= datetime.now(timezone.utc):
            err_msg = "Error: Start datetime to schedule a new appointment must be in the future, but is: {start_datetime}"
            self.logger.info(err_msg)
            raise ValueError(err_msg)

        end_datetime_utc = self._calculate_end_datetime(start_datetime_utc, duration_minutes)
        if not end_datetime_utc:
            self.logger.info("Error: Invalid start_datetime or duration_minutes")
            return None

        # Convert to UTC
        start_datetime_utc_str = self._get_str_from_datetime(start_datetime_utc)
        end_datetime_utc_str = self._get_str_from_datetime(end_datetime_utc)
        
        self.logger.info("Creating the Event...")
        
        headers = {
            'Authorization': f'Bearer {self._access_token}',
            'Content-Type': 'application/json'
        }
        
        # Prepare event payload
        payload_event = {
            'Subject': subject,
            'StartDateTime': start_datetime_utc_str,
            'EndDateTime': end_datetime_utc_str
        }        
        if description:
            payload_event['Description'] = description
        if location:
            payload_event['Location'] = location
        if owner_id:
            payload_event['OwnerId'] = owner_id
        if what_id:
            payload_event['WhatId'] = what_id
        if who_id:
            payload_event['WhoId'] = who_id
        
        url_creation_event = f"{self._instance_url}/services/data/{self._version_api}/sobjects/Event/"
        event_id = None
        exception_upon_creation = False
        async with httpx.AsyncClient() as client:
            
            try:
                resp_event = await client.post(url_creation_event, headers=headers, data=json.dumps(payload_event))
                if resp_event.status_code >= 200 and resp_event.status_code <= 299:
                    event_id = resp_event.json().get('id', None)
                    self.logger.info("Event created successfully!")
                    self.logger.info(f"ID: {event_id}")
                    self.logger.info(f"{self._instance_url}/lightning/r/Event/{event_id}/view")
                else:
                    self.logger.info(f"Error while creating the Event: {resp_event.status_code}")
                    try:
                        self.logger.info(json.dumps(resp_event.json(), indent=2, ensure_ascii=False))
                    except:
                        self.logger.info(resp_event.text)
            except Exception as e:
                exception_upon_creation = True

            # Verify the appointment was actually created
            verified_event_id = await self.check_for_appointment_creation(
                event_id=event_id,
                expected_subject=subject,
                start_datetime=start_datetime,
                duration_minutes=duration_minutes
            )
            
            if not verified_event_id:
                if exception_upon_creation:
                    self.logger.error(f"Exception while creating event.")
                
                # Retry recursively if max_retries > 0
                if max_retries > 0:
                    self.logger.info(f"Verification failed, retrying in {retry_delay}s... ({max_retries} retries remaining)")
                    await asyncio.sleep(retry_delay)
                    
                    # Recursive call with decremented max_retries
                    return await self.schedule_new_appointment_async(
                        subject=subject,
                        start_datetime=start_datetime,
                        duration_minutes=duration_minutes,
                        description=description,
                        location=location,
                        owner_id=owner_id,
                        what_id=what_id,
                        who_id=who_id,
                        max_retries=max_retries - 1,
                        retry_delay=retry_delay
                    )
                else:
                    self.logger.error("All retry attempts exhausted, appointment scheduling failed")
                    
            return verified_event_id

    async def check_for_appointment_creation(self, event_id: str | None, expected_subject: str, start_datetime: str, duration_minutes: int = 60) -> str | None:
        """Check if an appointment was successfully created by verifying its existence
        
        Args:
            event_id: The ID of the created event to verify (can be None)
            expected_subject: The expected subject of the appointment
            start_datetime: Expected start date and time in ISO format (e.g., '2025-05-20T14:00:00Z')
            duration_minutes: Expected duration in minutes (default: 60)
            
        Returns:
            The event_id if the appointment exists and matches expected parameters, None otherwise
        """

        # Calculate end datetime for the search window
        start_dt = self._get_french_datetime_from_str(start_datetime)
        if start_dt is None:
            self.logger.info("Error: Invalid start_datetime format for verification")
            return None

        # Convert back to UTC for API call
        french_now = datetime.now(pytz.timezone('Europe/Paris'))
        utc_offset_hours = (french_now.utcoffset().total_seconds() or 0) / 3600        
        if utc_offset_hours != 0:
            start_dt = start_dt - timedelta(hours=utc_offset_hours)

        start_datetime_utc = self._to_utc_datetime(start_dt)
        end_datetime_utc = self._calculate_end_datetime(start_datetime_utc, duration_minutes)
        
        # Create a small time window around the expected appointment time
        search_start = start_datetime_utc - timedelta(minutes=5)  # 5 minutes before
        search_end = end_datetime_utc + timedelta(minutes=5)      # 5 minutes after
        
        search_start_str = self._get_str_from_datetime(search_start)
        search_end_str = self._get_str_from_datetime(search_end)
        
        if event_id:
            self.logger.info(f"Verifying appointment creation for event ID: {event_id}")
        else:
            self.logger.info(f"Searching for appointment with subject: {expected_subject}")
        
        try:
            # Get appointments in the time window
            appointments = await self.get_scheduled_appointments_async(search_start_str, search_end_str)
            
            if appointments is None:
                self.logger.info("Error: Failed to retrieve appointments for verification")
                return None
            
            # Look for the specific appointment
            for appointment in appointments:
                # If event_id is provided, check both ID and subject
                if event_id:
                    if (appointment.get('Id') == event_id and 
                        appointment.get('Subject') == expected_subject):
                        self.logger.info(f"Appointment verification successful - Event ID: {event_id}")
                        return event_id
                else:
                    # If event_id is None, only check subject and return the found event_id
                    if appointment.get('Subject') == expected_subject:
                        found_event_id = appointment.get('Id')
                        self.logger.info(f"Appointment found with subject '{expected_subject}' - Event ID: {found_event_id}")
                        return found_event_id
            
            if event_id:
                self.logger.warning(f"Appointment not found during verification - Event ID: {event_id}")
            else:
                self.logger.warning(f"Appointment not found with subject: {expected_subject}")
            return None
            
        except Exception as e:
            self.logger.error(f"Error during appointment verification: {str(e)}")
            return None

    async def get_scheduled_appointments_async(self, start_datetime: str, end_datetime: str, owner_id: str | None = None) -> list | None:
        """Get events from Salesforce calendar between specified start and end datetimes
        
        Args:
            start_datetime: Start date and time in ISO format (e.g., '2025-05-20T14:00:00Z')
            end_datetime: End date and time in ISO format (e.g., '2025-05-20T15:00:00Z')
            owner_id: Optional Salesforce ID to filter events by owner
            
        Returns:
            List of events if successful, None otherwise
        """
        await self._ensure_authenticated_async()
        self.logger.info("Retrieving events...")
        
        # Prepare headers
        headers = {
            'Authorization': f'Bearer {self._access_token}',
            'Content-Type': 'application/json'
        }
        
        # Build SOQL query
        query = "SELECT Id, Subject, Description, StartDateTime, EndDateTime, Location, OwnerId, WhatId, WhoId "
        query += "FROM Event "
        query += f"WHERE StartDateTime >= {start_datetime} AND EndDateTime <= {end_datetime} "
        
        # Add owner filter if specified
        if owner_id:
            query += f"AND OwnerId = '{owner_id}' "
            
        query += "ORDER BY StartDateTime ASC "
        
        # URL encode the query
        encoded_query = urllib.parse.quote(query)
        self.logger.info(f"SOQL Query: {query}")
        
        # Create query URL
        url_query = f"{self._instance_url}/services/data/{self._version_api}/query/?q={encoded_query}"
        
        start_date_formated = start_datetime if "T" in start_datetime else f"{start_datetime}T"
        end_date_formated = end_datetime if "T" in end_datetime else f"{end_datetime}T"
        #
        if start_date_formated.endswith("T"): start_date_formated += "00:00:00"
        if end_date_formated.endswith("T"): end_date_formated += "23:59:59"
        #
        if not start_date_formated.endswith("Z"): start_date_formated += "Z"
        if not end_date_formated.endswith("Z"): end_date_formated += "Z"

        # Send request
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url_query, headers=headers)
                
                if resp.status_code == 200:
                    data = resp.json()
                    local_tz = pytz.timezone('Europe/Paris')

                    def convert_times(records):
                        processed_events = []
                        for event in records:
                            if event.get('StartDateTime'):
                                utc_dt = datetime.fromisoformat(event['StartDateTime'].replace('Z', '+00:00'))
                                event['StartDateTime'] = utc_dt.astimezone(local_tz).isoformat()
                            if event.get('EndDateTime'):
                                utc_dt = datetime.fromisoformat(event['EndDateTime'].replace('Z', '+00:00'))
                                event['EndDateTime'] = utc_dt.astimezone(local_tz).isoformat()
                            processed_events.append(event)
                        return processed_events

                    events = convert_times(data.get('records', []))
                    total_size = data.get('totalSize', 0)
                    self.logger.info(f"Retrieved {total_size} events")
                    
                    # Handle pagination if needed
                    next_records_url = data.get('nextRecordsUrl')
                    while next_records_url:
                        next_url = f"{self._instance_url}{next_records_url}"
                        resp = await client.get(next_url, headers=headers)
                        if resp.status_code == 200:
                            next_data = resp.json()
                            events.extend(convert_times(next_data.get('records', [])))
                            next_records_url = next_data.get('nextRecordsUrl')
                        else:
                            self.logger.info(f"Error retrieving additional events: {resp.status_code}")
                            break
                    return events
                else:
                    self.logger.info(f"Error retrieving events: {resp.status_code}")
                    try:
                        self.logger.info(json.dumps(resp.json(), indent=2, ensure_ascii=False))
                    except:
                        self.logger.info(resp.text)
                    return None
            except Exception as e:
                self.logger.info(f"Error retrieving events: {str(e)}")
                return None

    async def delete_event_by_id_async(self, event_id: str) -> bool:
        await self._ensure_authenticated_async()
        headers = {
            'Authorization': f'Bearer {self._access_token}',
            'Content-Type': 'application/json'
        }
        
        url_deletion_event = f"{self._instance_url}/services/data/{self._version_api}/sobjects/Event/{event_id}"
        
        async with httpx.AsyncClient() as client:
            try:
                resp_event = await client.delete(url_deletion_event, headers=headers)
                
                if resp_event.status_code == 204:
                    self.logger.info("Event deleted successfully!")
                    return True
                else:
                    self.logger.info(f"Error while deleting the Event: {resp_event.status_code}")
                    try:
                        self.logger.info(json.dumps(resp_event.json(), indent=2, ensure_ascii=False))
                    except:
                        self.logger.info(resp_event.text)
                    return False
            except Exception as e:
                self.logger.error(f"Error deleting event: {str(e)}")
                return False

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
        await self._ensure_authenticated_async()
        headers = {
            'Authorization': f'Bearer {self._access_token}',
            'Content-Type': 'application/json'
        }

        # For long-running apps, consider creating httpx.AsyncClient once and reusing it.
        async with httpx.AsyncClient() as client:
            # --- Try to find a Contact ---
            contact_query = (
                "SELECT Id, Contact.Salutation, Contact.FirstName, Contact.LastName, Contact.Email, Contact.Phone, Contact.MobilePhone, Account.Id, Account.Name, Owner.Id, Owner.Name "
                "FROM Contact "
                f"WHERE Phone = '{phone_number}' OR MobilePhone = '{phone_number}' "
                "LIMIT 1"
            )
            self.logger.debug(f"SOQL Query (Contact): {contact_query}")
            encoded_contact_query = urllib.parse.quote(contact_query)
            url_contact_query = f"{self._instance_url}/services/data/{self._version_api}/query/?q={encoded_contact_query}"

            try:
                resp = await client.get(url_contact_query, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                records = data.get('records', [])
                if records:
                    contact_data = records[0]
                    self.logger.info(f"Found Contact: Id= {contact_data.get('Id')}, Name= {contact_data.get('FirstName')} {contact_data.get('LastName')}")
                    return {'type': 'Contact', 'data': contact_data}
            except httpx.HTTPStatusError as http_err:
                self.logger.info(f"HTTP error querying Contact: {http_err} - Status: {http_err.response.status_code}")
                try:
                    self.logger.info(json.dumps(http_err.response.json(), indent=2, ensure_ascii=False))
                except json.JSONDecodeError:
                    self.logger.info(http_err.response.text)
            except httpx.RequestError as req_err:
                self.logger.info(f"Request error querying Contact: {str(req_err)}")
            except Exception as e:
                self.logger.info(f"Generic exception querying Contact: {str(e)}")

            # --- If no Contact found, try to find a Lead ---
            lead_query = (
                "SELECT Id, Lead.FirstName, Lead.LastName, Lead.Email, Lead.Phone, Lead.MobilePhone, Lead.Company, Lead.Owner.Id, Lead.Owner.Name, Lead.Status, Lead.IsConverted "
                "FROM Lead "
                f"WHERE (Phone = '{phone_number}' OR MobilePhone = '{phone_number}') AND IsConverted = false "
                "LIMIT 1"
            )
            self.logger.debug(f"SOQL Query (Lead): {lead_query}")
            encoded_lead_query = urllib.parse.quote(lead_query)
            url_lead_query = f"{self._instance_url}/services/data/{self._version_api}/query/?q={encoded_lead_query}"

            try:
                resp = await client.get(url_lead_query, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                records = data.get('records', [])
                if records:
                    lead_data = records[0]
                    self.logger.info(f"Found Lead: {lead_data.get('Id')} - {lead_data.get('FirstName')} {lead_data.get('LastName')}")
                    return {'type': 'Lead', 'data': lead_data}
            except httpx.HTTPStatusError as http_err:
                self.logger.info(f"HTTP error querying Lead: {http_err} - Status: {http_err.response.status_code}")
                try:
                    self.logger.info(json.dumps(http_err.response.json(), indent=2, ensure_ascii=False))
                except json.JSONDecodeError:
                    self.logger.info(http_err.response.text)
            except httpx.RequestError as req_err:
                self.logger.info(f"Request error querying Lead: {str(req_err)}")
            except Exception as e:
                self.logger.info(f"Generic exception querying Lead: {str(e)}")
            
            self.logger.info(f"No Contact or non-converted Lead found for phone number: {phone_number}")
            return None


    async def get_persons_async(self) -> list[dict]:
        """
        Retrieve lestest Contacts and Leads from Salesforce (asynchronous).

        Returns:
            A list of dictionaries containing the person's type ('Contact' or 'Lead') and data.
        """
        await self._ensure_authenticated_async()
        headers = {
            'Authorization': f'Bearer {self._access_token}',
            'Content-Type': 'application/json'
        }

        # For long-running apps, consider creating httpx.AsyncClient once and reusing it.
        async with httpx.AsyncClient() as client:
            # --- Try to find a Contact ---
            contact_query = (
                "SELECT Id, Contact.Salutation, Contact.FirstName, Contact.LastName, Contact.Email, Contact.Phone, Contact.MobilePhone, Account.Id, Account.Name, Owner.Id, Owner.Name "
                "FROM Contact "
                "WHERE Id != null "
                "ORDER BY Id DESC "
                "LIMIT 10"
            )
            self.logger.debug(f"SOQL Query (Contact): {contact_query}")
            encoded_contact_query = urllib.parse.quote(contact_query)
            url_contact_query = f"{self._instance_url}/services/data/{self._version_api}/query/?q={encoded_contact_query}"

            try:
                resp = await client.get(url_contact_query, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                records = data.get('records', [])
                all_contacts = []
                for record in records:
                    self.logger.info(f"Found Contact: {record.get('Id')} - {record.get('FirstName')} {record.get('LastName')}")
                    all_contacts.append(record)
                return all_contacts
            except httpx.HTTPStatusError as http_err:
                self.logger.error(f"HTTP error querying Contact: {http_err} - Status: {http_err.response.status_code}")
                try:
                    self.logger.error(json.dumps(http_err.response.json(), indent=2, ensure_ascii=False))
                except json.JSONDecodeError:
                    self.logger.error(http_err.response.text)
            except httpx.RequestError as req_err:
                self.logger.error(f"Request error querying Contact: {str(req_err)}")
            except Exception as e:
                self.logger.error(f"Generic exception querying Contact: {str(e)}")
            
            return None

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
        await self._ensure_authenticated_async()

        headers = {'Authorization': f'Bearer {self._access_token}'}
        schema = {}

        async with httpx.AsyncClient() as client:
            # 1. Get list of all SObjects metadata for URLs
            all_sobjects_url = f"{self._instance_url}/services/data/{self._version_api}/sobjects/"
            try:
                self.logger.info("Fetching list of all SObjects...")
                resp = await client.get(all_sobjects_url, headers=headers)
                resp.raise_for_status()
                all_sobjects_data = resp.json()
            except httpx.HTTPStatusError as http_err_main:
                self.logger.error(f"HTTP error getting SObject list: {http_err_main} - Status: {http_err_main.response.status_code}")
                try: self.logger.error(json.dumps(http_err_main.response.json(), indent=2))
                except: self.logger.error(http_err_main.response.text)
                return None
            except Exception as e_main:
                self.logger.error(f"Error fetching SObject list: {str(e_main)}")
                return None

            # Determine the list of SObjects to describe
            target_sobjects_info = []
            all_sobjects_metadata_list = all_sobjects_data.get('sobjects', [])

            if sobjects_to_describe:
                s_name_to_url_map = {s_info['name']: s_info['urls']['describe'] 
                                     for s_info in all_sobjects_metadata_list 
                                     if 'name' in s_info and 'urls' in s_info and 'describe' in s_info['urls']}
                for s_name in sobjects_to_describe:
                    if s_name in s_name_to_url_map:
                        target_sobjects_info.append({'name': s_name, 'describe_url_path': s_name_to_url_map[s_name]})
                    else: # Fallback to constructing the URL if not found (e.g. object not in global list, or list was partial)
                        target_sobjects_info.append({'name': s_name, 'describe_url_path': f"/services/data/{self._version_api}/sobjects/{s_name}/describe/"})
                self.logger.info(f"Will describe {len(target_sobjects_info)} specified SObjects: {', '.join(s_name for s_name in sobjects_to_describe)}")
            else:
                target_sobjects_info = [{'name': s_info['name'], 'describe_url_path': s_info['urls']['describe']}
                                       for s_info in all_sobjects_metadata_list
                                       if 'name' in s_info and 'urls' in s_info and 'describe' in s_info['urls']]
                self.logger.info(f"Found {len(target_sobjects_info)} SObjects. Describing all can be very slow and consume many API calls.")

            total_objects_to_describe = len(target_sobjects_info)
            for i, sobject_item in enumerate(target_sobjects_info):
                s_name = sobject_item['name']
                describe_url = f"{self._instance_url}{sobject_item['describe_url_path']}"
                
                self.logger.info(f"Describing SObject {i+1}/{total_objects_to_describe}: {s_name}...")
                try:
                    desc_resp = await client.get(describe_url, headers=headers)
                    desc_resp.raise_for_status()
                    s_description = desc_resp.json()
                    
                    fields_info = {}
                    for field in s_description.get('fields', []):
                        field_name = field.get('name')
                        is_pk = (field_name == 'Id')
                        is_fk = field.get('type') == 'reference' and bool(field.get('referenceTo'))
                        
                        if include_fields or is_pk or is_fk:
                            fields_info[field_name] = {
                                'label': field.get('label'),
                                'type': field.get('type'),
                                'length': field.get('length', 0) if field.get('type') in ['string', 'textarea', 'phone', 'url', 'email', 'picklist', 'multipicklist', 'combobox', 'id', 'reference'] else None,
                                'precision': field.get('precision') if field.get('type') in ['currency', 'double', 'percent', 'int', 'long'] else None,
                                'scale': field.get('scale') if field.get('type') in ['currency', 'double', 'percent'] else None,
                                'nillable': field.get('nillable'),
                                'custom': field.get('custom'),
                                'is_primary_key': is_pk,
                                'is_foreign_key': is_fk,
                                'references_to': field.get('referenceTo', []) if is_fk else []
                            }
                    schema[s_name] = {'fields': fields_info}
                    
                    # Brief pause to avoid hitting rate limits too hard
                    if total_objects_to_describe > 10 and i < total_objects_to_describe - 1:
                        await asyncio.sleep(0.2) # 200ms delay

                except httpx.HTTPStatusError as http_err_desc:
                    error_detail = "Unknown error"
                    try: error_detail = json.dumps(http_err_desc.response.json(), indent=2)
                    except: error_detail = http_err_desc.response.text
                    self.logger.info(f"HTTP error describing SObject {s_name}: {http_err_desc} - Status: {http_err_desc.response.status_code}. Details: {error_detail[:500]}")
                    schema[s_name] = {'error': f'Failed to describe: {str(http_err_desc)}'}
                except Exception as e_desc:
                    self.logger.info(f"Error describing SObject {s_name}: {str(e_desc)}")
                    schema[s_name] = {'error': f'Failed to describe: {str(e_desc)}'}
        
        return schema

    ## Internal helpers ##

    def _get_french_datetime_from_str(self, datetime_str: str) -> datetime | None:
        pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$'
        if not re.match(pattern, datetime_str):
            self.logger.info(f"Invalid 'datetime_str' paramter format: {datetime_str}")
            self.logger.info("datetime_str must be in the format 'YYYY-MM-DDTHH:MM:SSZ', like: '2025-06-15T23:59:59Z'")
            return None
        start_dt = datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%SZ")
        start_dt_utc = start_dt.replace(tzinfo=pytz.utc)
        french_tz = pytz.timezone('Europe/Paris')
        return start_dt_utc.astimezone(french_tz)

    def _get_str_from_datetime(self, dt: datetime) -> str:
        """Convert a datetime to a string in the format 'YYYY-MM-DDTHH:MM:SSZ'"""
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _to_utc_datetime(self, dt: datetime) -> datetime:
        """Convert a naive or local-aware datetime to UTC-aware datetime."""
        if dt.tzinfo is None:
            # Assume naive datetimes are in local time; convert to UTC
            return dt.astimezone(timezone.utc)
        return dt.astimezone(timezone.utc)

    def _calculate_end_datetime(self, start_datetime: datetime, duration_minutes: int) -> datetime | None:
        return start_datetime + timedelta(minutes=duration_minutes)
            
    async def _query_salesforce(self, soql_query: str) -> dict | None:
        """Helper method to execute a SOQL query and return the full JSON response.

        Args:
            soql_query: The SOQL query string.

        Returns:
            The full JSON response dictionary from Salesforce (includes 'records',
            'totalSize', 'done', 'nextRecordsUrl'), or None if an error occurs.
        """
        # Authentication should be ensured by the public calling method using _ensure_authenticated
        if not self._access_token or not self._instance_url:
             # This state should ideally not be reached if _ensure_authenticated was called.
            self.logger.info("Critical Error: _query_salesforce called without prior successful authentication.")
            return None

        headers = {'Authorization': f'Bearer {self._access_token}'}
        encoded_query = urllib.parse.quote(soql_query)
        url_query = f"{self._instance_url}/services/data/{self._version_api}/query/?q={encoded_query}"
        
        # self.logger.info(f"Executing SOQL: {soql_query}") # Verbose, enable for deep debugging
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url_query, headers=headers)
                resp.raise_for_status() # Will raise HTTPStatusError for 4xx/5xx status codes
                return resp.json()
            except httpx.HTTPStatusError as http_err:
                error_message = f"SOQL Query HTTP error: {http_err} - Status: {http_err.response.status_code}. Query: {soql_query}"
                self.logger.info(error_message)
                try: 
                    error_details = http_err.response.json()
                    self.logger.info(json.dumps(error_details, indent=2, ensure_ascii=False))
                except json.JSONDecodeError:
                    self.logger.info(f"Response text: {http_err.response.text}")
                return None
            except Exception as e:
                self.logger.info(f"SOQL Query general error: {str(e)}. Query: {soql_query}")
                return None

    async def get_leads_by_details_async(self, email: str | None = None, first_name: str | None = None, last_name: str | None = None, company_name: str | None = None) -> list[dict] | None:
        """
        Retrieve active (non-converted) Leads based on email, name, or company (asynchronous).
        Args:
            email: Email address to search for.
            first_name: First name to search for (requires last_name for effective name search).
            last_name: Last name to search for (requires first_name for effective name search).
            company_name: Company name to search for.
        Returns:
            A list of matching Lead dictionaries, or None if a query error occurs.
            Returns an empty list if no matches are found but the query was successful.
        """
        await self._ensure_authenticated_async()

        conditions = ["IsConverted = false"]
        if email:
            conditions.append(f"Email = '{email}'")
        if first_name and last_name:
            conditions.append(f"(FirstName = '{first_name}' AND LastName = '{last_name}')")
        elif first_name or last_name:
            self.logger.info("Warning: For name-based Lead search, providing both first_name and last_name is recommended for accuracy.")
            if first_name: conditions.append(f"FirstName = '{first_name}'")
            if last_name: conditions.append(f"LastName = '{last_name}'")
        if company_name:
            conditions.append(f"Company = '{company_name}'")

        if len(conditions) == 1: # Only IsConverted = false, no other criteria
            self.logger.info("Error: At least one search criterion (email, full name, or company) must be provided for get_leads_by_details_async.")
            return None # Or an empty list if that's preferred for bad input

        query_filter = " AND " + " AND ".join(f"({c})" for c in conditions[1:])
        
        soql_query = (
            "SELECT Id, FirstName, LastName, Email, Company, Status, Owner.Name, CreatedDate "
            "FROM Lead "
            f"WHERE {conditions[0]} {query_filter} "
            "ORDER BY CreatedDate DESC LIMIT 200" # Added LIMIT for safety
        )
        
        response_data = await self._query_salesforce(soql_query)
        if response_data and response_data.get('records') is not None:
            return response_data['records']
        elif response_data is None: # Error occurred in _query_salesforce
            return None
        else: # Query successful, but no records found (e.g. response_data['records'] is empty list)
            return []

    async def get_opportunities_for_lead_async(self, lead_id: str) -> list[dict] | None:
        """
        Retrieve Opportunities related to a specific Lead, primarily if converted (asynchronous).
        Args:
            lead_id: The ID of the Salesforce Lead.
        Returns:
            A list of Opportunity dictionaries. Prioritizes ConvertedOpportunityId,
            then searches by ConvertedAccountId. Returns None on error, empty list if no related Opps found.
        """
        await self._ensure_authenticated_async()

        if not lead_id:
            self.logger.info("Error: lead_id must be provided.")
            return None

        # Step 1: Get Lead conversion details
        lead_info_soql = f"SELECT Id, IsConverted, ConvertedOpportunityId, ConvertedAccountId FROM Lead WHERE Id = '{lead_id}'"
        lead_response = await self._query_salesforce(lead_info_soql)

        if not lead_response or lead_response.get('records') is None:
            # _query_salesforce would have printed an error if lead_response is None
            # If records is None (but lead_response isn't), or empty, Lead not found or query issue.
            if lead_response and lead_response.get('totalSize', 0) == 0:
                 self.logger.info(f"Lead with ID '{lead_id}' not found.")
                 return []
            return None # Error occurred during query
        
        lead_data = lead_response['records'][0]
        is_converted = lead_data.get('IsConverted')
        converted_opp_id = lead_data.get('ConvertedOpportunityId')
        converted_acc_id = lead_data.get('ConvertedAccountId')

        opportunity_soql = ""
        common_opp_fields = "SELECT Id, Name, StageName, Amount, CloseDate, AccountId, Account.Name, Owner.Name, CreatedDate FROM Opportunity"

        if is_converted and converted_opp_id:
            self.logger.info(f"Lead '{lead_id}' was converted to Opportunity ID: '{converted_opp_id}'. Fetching this Opportunity.")
            opportunity_soql = f"{common_opp_fields} WHERE Id = '{converted_opp_id}' LIMIT 1"
        elif is_converted and converted_acc_id:
            self.logger.info(f"Lead '{lead_id}' was converted to Account ID: '{converted_acc_id}'. Searching Opportunities for this Account.")
            opportunity_soql = f"{common_opp_fields} WHERE AccountId = '{converted_acc_id}' ORDER BY CreatedDate DESC LIMIT 200"
        else:
            self.logger.info(f"Lead '{lead_id}' is not converted, or no ConvertedOpportunityId/ConvertedAccountId found. No direct Opportunities from conversion.")
            return []

        if not opportunity_soql: # Should not happen if logic above is correct, but as a safeguard.
            return []

        opp_response = await self._query_salesforce(opportunity_soql)
        if opp_response and opp_response.get('records') is not None:
            return opp_response['records']
        elif opp_response is None: # Error in _query_salesforce
            return None 
        else: # Query successful, but no records (e.g. opp_response['records'] is empty list)
            return []
