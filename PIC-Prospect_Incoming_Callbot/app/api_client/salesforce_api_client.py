import asyncio
import json
import logging
import re
import time
import urllib.parse
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytz
from .calendar_client_interface import CalendarClientInterface
from .salesforce_user_client_interface import SalesforceUserClientInterface
from utils.envvar import EnvHelper
from utils.latency_decorator import measure_latency
from utils.latency_metric import OperationType


class SalesforceApiClient(CalendarClientInterface, SalesforceUserClientInterface):
    _client_id = "3MVG9IKwJOi7clC2.8QIzh9BkM6NhU53bup6EUfFQiXJ01nh.l2YJKF5vbNWqPkFEdjgzAXIqK3U1p2WCBUD3"
    _username = EnvHelper.get_salesforce_username()
    _password = EnvHelper.get_salesforce_password()
    _client_secret = EnvHelper.get_salesforce_client_secret()
    _private_key_file = EnvHelper.get_salesforce_private_key_file_path()
    _consumer_key = EnvHelper.get_salesforce_consumer_key()
    _private_key_file_jwt = EnvHelper.get_salesforce_private_key_file()
    _auth_method = EnvHelper.get_salesforce_auth_method()
    _is_sandbox = True

    # Static class-level authentication tokens (shared across all instances)
    _static_access_token = None
    _static_instance_url = None
    _static_token_expiry = None

    def __init__(
        self,
        client_id: str | None = None,
        username: str | None = None,
        private_key_file: str | None = None,
        is_sandbox: bool = True,
        auth_method: str | None = None,
        consumer_key: str | None = None,
        private_key_file_jwt: str | None = None,
        salesforce_url: str | None = None,
    ):
        self.logger = logging.getLogger(__name__)
        salesforce_domain = "salesforce.com"
        self.subdomain = "test" if is_sandbox else "login"
        self._salesforce_url = f"https://{self.subdomain}.{salesforce_domain}"
        self._auth_url = f"{self._salesforce_url}/services/oauth2/token"
        self._client_id = client_id or self._client_id
        self._username = username or self._username
        self._private_key_file = private_key_file or self._private_key_file
        self._consumer_key = consumer_key or self._consumer_key
        self._private_key_file_jwt = private_key_file_jwt or self._private_key_file_jwt
        self._auth_method = auth_method or self._auth_method
        self._is_sandbox = is_sandbox or self._is_sandbox
        self._version_api = "v60.0"

        self.authenticate()

    @classmethod
    def _is_authenticated(cls) -> bool:
        """Check if we have a valid static authentication token"""
        if not cls._static_access_token or not cls._static_instance_url:
            return False

        # Check if token is expired (if we have expiry info)
        if cls._static_token_expiry and datetime.now(UTC) >= cls._static_token_expiry:
            cls._static_access_token = None
            cls._static_instance_url = None
            cls._static_token_expiry = None
            return False

        return True

    @property
    def _access_token(self) -> str | None:
        """Get the current access token (static or None)"""
        return self.__class__._static_access_token

    @property
    def _instance_url(self) -> str | None:
        """Get the current instance URL (static or None)"""
        return self.__class__._static_instance_url

    def authenticate(self) -> bool:
        """Authenticate with Salesforce using JWT or password method based on configuration"""
        # Check if already authenticated
        if self._is_authenticated():
            self.logger.info(f"Already authenticated with Salesforce, skipping authentication")
            return True

        self.logger.info(f"Salesforce Authentication in progress using {self._auth_method} method...")

        if self._auth_method.lower() == "jwt":
            return self._authenticate_jwt()
        else:
            return self._authenticate_password()

    def _authenticate_jwt(self) -> bool:
        """Authenticate with Salesforce using JWT Bearer Token flow"""
        self.logger.info("Using JWT authentication")

        # Validate required JWT parameters
        if not self._consumer_key:
            self.logger.error("Error: SALESFORCE_CONSUMER_KEY is required for JWT authentication")
            return False
        if not self._username:
            self.logger.error("Error: SALESFORCE_USERNAME is required for JWT authentication")
            return False
        if not self._private_key_file_jwt:
            self.logger.error("Error: SALESFORCE_PRIVATE_KEY_FILE is required for JWT authentication")
            return False

        # Use salesforce_url if provided, otherwise use auth_url
        audience_url = self._salesforce_url if self._salesforce_url else self._auth_url

        try:
            # Read private key file
            with open(self._private_key_file_jwt, 'r', encoding='utf-8') as f:
                private_key = f.read()

            self.logger.debug(f"Using private key from: {self._private_key_file_jwt}")

        except FileNotFoundError:
            self.logger.error(f"Error: Private key file '{self._private_key_file_jwt}' not found")
            self.__class__._static_access_token = None
            self.__class__._static_instance_url = None
            self.__class__._static_token_expiry = None
            return False
        except Exception as e:
            self.logger.error(f"Error reading private key file: {e!s}")
            self.__class__._static_access_token = None
            self.__class__._static_instance_url = None
            self.__class__._static_token_expiry = None
            return False

        try:
            # Create JWT payload
            payload = {
                'iss': self._consumer_key,  # Issuer (Consumer Key from Connected App)
                'sub': self._username,      # Subject (Salesforce username)
                'aud': audience_url,        # Audience (Salesforce URL)
                'exp': int(time.time()) + 300  # Expiration (5 minutes from now)
            }

            self.logger.debug(f"JWT payload: iss={self._consumer_key}, sub={self._username}, aud={audience_url}")

            # Encode JWT using RS256 algorithm
            jwt_token = jwt.encode(payload, private_key, algorithm='RS256')

            # Prepare authentication request
            params = {
                'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                'assertion': jwt_token
            }

            # Send authentication request
            with httpx.Client() as client:
                response = client.post(self._auth_url, data=params)
                response.raise_for_status()

                # Process response
                auth_data = response.json()
                access_token = auth_data.get("access_token")
                instance_url = auth_data.get("instance_url")

                if access_token and instance_url:
                    # Store tokens in static class variables
                    self.__class__._static_access_token = access_token
                    self.__class__._static_instance_url = instance_url
                    # Set expiry time based on JWT payload expiration (5 minutes from now)
                    self.__class__._static_token_expiry = datetime.now(UTC) + timedelta(minutes=4)  # 4 minutes to be safe
                    self.logger.info("JWT Authentication successful.")
                    return True
                else:
                    error_msg = "JWT Authentication completed but access_token or instance_url is missing."
                    if not access_token:
                        error_msg += " Access token is missing."
                    if not instance_url:
                        error_msg += " Instance URL is missing."
                    self.logger.error(error_msg)
                    self.__class__._static_access_token = None
                    self.__class__._static_instance_url = None
                    self.__class__._static_token_expiry = None
                    return False

        except jwt.InvalidKeyError as e:
            self.logger.error(f"JWT Invalid key error: {e!s}")
            self.__class__._static_access_token = None
            self.__class__._static_instance_url = None
            self.__class__._static_token_expiry = None
            return False
        except httpx.HTTPStatusError as e:
            self.logger.error(f"JWT Authentication HTTP error: {e.response.status_code} - {e.response.text}")
            self.__class__._static_access_token = None
            self.__class__._static_instance_url = None
            self.__class__._static_token_expiry = None
            return False
        except Exception as e:
            self.logger.error(f"JWT Authentication error: {e!s}")
            self.__class__._static_access_token = None
            self.__class__._static_instance_url = None
            self.__class__._static_token_expiry = None
            return False

    def _authenticate_password(self) -> bool:
        """Authenticate with Salesforce using password flow (legacy method)"""
        self.logger.info("Using password authentication")

        # Validate required password parameters
        if not self._client_id:
            self.logger.error("Error: Client ID is required for password authentication")
            return False
        if not self._client_secret:
            self.logger.error("Error: SALESFORCE_CLIENT_SECRET is required for password authentication")
            return False
        if not self._username:
            self.logger.error("Error: SALESFORCE_USERNAME is required for password authentication")
            return False
        if not self._password:
            self.logger.error("Error: SALESFORCE_PASSWORD is required for password authentication")
            return False

        params = {
            "grant_type": "password",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "username": self._username,
            "password": self._password,
        }

        # Send authentication request
        with httpx.Client() as client:
            try:
                response = client.post(self._auth_url, data=params)
                response.raise_for_status()

                # Process response
                auth_data = response.json()
                access_token = auth_data.get("access_token")
                instance_url = auth_data.get("instance_url")

                if access_token and instance_url:
                    # Store tokens in static class variables
                    self.__class__._static_access_token = access_token
                    self.__class__._static_instance_url = instance_url
                    # Password tokens typically last longer, set expiry to 1 hour
                    self.__class__._static_token_expiry = datetime.now(UTC) + timedelta(hours=1)
                    self.logger.info("Password Authentication successful.")
                    return True
                else:
                    error_msg = "Password Authentication completed but access_token or instance_url is missing."
                    if not access_token:
                        error_msg += " Access token is missing."
                    if not instance_url:
                        error_msg += " Instance URL is missing."
                    self.logger.error(error_msg)
                    self.__class__._static_access_token = None  # Ensure clean state
                    self.__class__._static_instance_url = None
                    self.__class__._static_token_expiry = None
                    return False

            except httpx.HTTPStatusError as e:
                self.logger.error(f"Password Authentication HTTP error: {e.response.status_code} - {e.response.text}")
                self.__class__._static_access_token = None
                self.__class__._static_instance_url = None
                self.__class__._static_token_expiry = None
                return False
            except Exception as e:
                self.logger.error(f"Password Authentication error: {e!s}")
                self.__class__._static_access_token = None
                self.__class__._static_instance_url = None
                self.__class__._static_token_expiry = None
                return False

    @classmethod
    def clear_authentication_cache(cls):
        """Clear the static authentication cache to force re-authentication"""
        cls._static_access_token = None
        cls._static_instance_url = None
        cls._static_token_expiry = None

    async def _ensure_authenticated_async(self):
        if not self._is_authenticated():
            if not self.authenticate():
                raise Exception("Salesforce authentication failed. Cannot proceed with API call.")

    @measure_latency(OperationType.SALESFORCE, provider="salesforce")
    async def schedule_new_appointment_async(
        self,
        subject: str,
        start_datetime: str,
        duration_minutes: int = 30,
        description: str | None = None,
        location: str | None = None,
        owner_id: str | None = None,
        what_id: str | None = None,
        who_id: str | None = None,
        max_retries: int = 2,
        retry_delay: float = 1.0,
    ) -> str | None:
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

        # Validate retry parameters
        if max_retries < 0:
            max_retries = 0  # Treat negative retries as zero
        if retry_delay < 0:
            retry_delay = 0  # Treat negative delay as zero

        # Check the calendar availability before creating the appointement
        verified_event_id = await self.verify_appointment_existance_async(
            event_id=None, expected_subject=subject, start_datetime=start_datetime, duration_minutes=duration_minutes
        )
        if verified_event_id:
            self.logger.error(
                f"Error during scheduling new appointment: an appointment already exists at the same time {start_datetime}, of Id: {verified_event_id}"
            )
            return None

        # Convert to UTC
        start_dt = self._get_french_datetime_from_str(start_datetime)
        if start_dt is None:
            self.logger.info("Error: Invalid start_datetime format")
            return None
        
        # Manually set timezone, because of issue within the docker container
        french_now = datetime.now(pytz.timezone("Europe/Paris"))
        utc_offset_hours = (french_now.utcoffset().total_seconds() or 0) / 3600
        if utc_offset_hours != 0:
            start_dt = start_dt - timedelta(hours=utc_offset_hours)
            self.logger.error(f"<<@>> UTC offset hours removed: {utc_offset_hours}")

        start_datetime_utc = self._to_utc_datetime(start_dt)

        if start_datetime_utc <= datetime.now(UTC):
            err_msg = (
                "Error: Start datetime to schedule a new appointment must be in the future, but is: {start_datetime}"
            )
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

        headers = {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}

        # Prepare event payload
        payload_event = {
            "Subject": subject,
            "StartDateTime": start_datetime_utc_str,
            "EndDateTime": end_datetime_utc_str,
        }
        if description:
            payload_event["Description"] = description
        if location:
            payload_event["Location"] = location
        if owner_id:
            payload_event["OwnerId"] = owner_id
        if what_id:
            payload_event["WhatId"] = what_id
        if who_id:
            payload_event["WhoId"] = who_id

        async def _execute_appointment_creation():
            url_creation_event = f"{self._instance_url}/services/data/{self._version_api}/sobjects/Event/"
            async with httpx.AsyncClient() as client:
                resp_event = await client.post(url_creation_event, headers=headers, data=json.dumps(payload_event))
                resp_event.raise_for_status()

                event_id = resp_event.json().get("id", None)
                self.logger.info("Event created successfully!")
                self.logger.info(f"ID: {event_id}")
                self.logger.info(f"{self._instance_url}/lightning/r/Event/{event_id}/view")

                # Verify the appointment was created successfully
                verified_event_id = await self.verify_appointment_existance_async(event_id=event_id, expected_subject=subject, start_datetime=start_datetime, duration_minutes=duration_minutes)
                if verified_event_id:
                    return verified_event_id
                else:
                    # Verification failed, return None to trigger retry
                    return None

        #####
        event_id = None
        exception_upon_creation = False

        try:
            event_id = await self._with_auth_retry(_execute_appointment_creation)
        except httpx.HTTPStatusError as http_err:
            self.logger.info(f"Error while creating the Event: {http_err.response.status_code}")
            try:
                self.logger.info(json.dumps(http_err.response.json(), indent=2, ensure_ascii=False))
            except Exception:
                self.logger.info(http_err.response.text)
            exception_upon_creation = True
        except Exception:
            exception_upon_creation = True

        if not event_id:
            if exception_upon_creation:
                self.logger.error("Exception while creating event.")

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
                    retry_delay=retry_delay,
                )
            else:
                self.logger.error("All retry attempts exhausted, appointment scheduling failed")

        return event_id

    @measure_latency(OperationType.SALESFORCE, provider="salesforce")
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
        if not start_datetime.endswith("Z"): start_datetime += "Z"
        
        # Calculate end datetime for the search window
        start_dt = self._get_french_datetime_from_str(start_datetime)
        if start_dt is None:
            self.logger.info("Error: Invalid start_datetime format for verification")
            return None

        # Convert back to UTC for API call
        french_now = datetime.now(pytz.timezone("Europe/Paris"))
        utc_offset_hours = (french_now.utcoffset().total_seconds() or 0) / 3600
        if utc_offset_hours != 0:
            start_dt = start_dt - timedelta(hours=utc_offset_hours)

        start_datetime_utc = self._to_utc_datetime(start_dt)
        end_datetime_utc = self._calculate_end_datetime(start_datetime_utc, duration_minutes)

        # Create a small time window around the expected appointment time
        search_start = start_datetime_utc - timedelta(minutes=5)  # 5 minutes before
        search_end = end_datetime_utc + timedelta(minutes=5)  # 5 minutes after

        search_start_str = self._get_str_from_datetime(search_start)
        search_end_str = self._get_str_from_datetime(search_end)

        if event_id:
            self.logger.info(f"Verifying appointment with event ID: {event_id}")
        elif expected_subject:
            self.logger.info(f"Searching for appointment with subject: {expected_subject}")
        else:
            self.logger.info("Searching for any appointment in the specified time window")

        try:
            # Get appointments in the time window
            appointments = await self.get_scheduled_appointments_async(search_start_str, search_end_str)

            if appointments is None:
                self.logger.info("Error: Failed to retrieve appointments for verification")
                return None

            if not appointments:
                self.logger.info("No appointments found in the specified time window")
                return None

            # Look for the specific appointment based on criteria
            for appointment in appointments:
                # If event_id is specified, check if it matches
                if event_id:
                    if appointment.get("Id") == event_id:
                        # Also check subject if provided
                        if expected_subject and appointment.get("Subject") != expected_subject:
                            continue
                        self.logger.info(f"Appointment verification successful - Event ID: {event_id}")
                        return event_id
                # If expected_subject is specified but no event_id, check subject match
                elif expected_subject:
                    if appointment.get("Subject") == expected_subject:
                        found_event_id = appointment.get("Id")
                        self.logger.info(f"Appointment found with subject '{expected_subject}' - Event ID: {found_event_id}")
                        return found_event_id

            # If neither event_id nor expected_subject specified, return first appointment's ID
            if not event_id and not expected_subject:
                first_appointment_id = appointments[0].get("Id")
                first_appointment_subject = appointments[0].get("Subject", "No subject")
                self.logger.info(f"First appointment found - Event ID: {first_appointment_id}, Subject: '{first_appointment_subject}'")
                return first_appointment_id

            # If we reach here, no matching appointment was found
            if event_id:
                self.logger.warning(f"Appointment not found with event ID: {event_id}")
            elif expected_subject:
                self.logger.warning(f"Appointment not found with subject: {expected_subject}")
            
            return None

        except Exception as e:
            self.logger.error(f"Error during appointment verification: {e!s}")
            return None

    @measure_latency(OperationType.SALESFORCE, provider="salesforce")
    async def get_scheduled_appointments_async(self, start_datetime: str, end_datetime: str, owner_id: str | None = None, user_id: str | None = None) -> list[dict]:
        """Get events from Salesforce calendar between specified start and end datetimes

        Args:
            start_datetime: Start date and time in ISO format (e.g., '2025-05-20T14:00:00Z')
            end_datetime: End date and time in ISO format (e.g., '2025-05-20T15:00:00Z')
            owner_id: Optional Salesforce ID to filter events by owner
            user_id: Optional Salesforce ID to filter events by user (WhoId)

        Returns:
            List of events if successful, None otherwise
        """
        await self._ensure_authenticated_async()
        self.logger.info("Retrieving events...")

        async def _execute_appointments_query() -> list:
            # Prepare headers
            headers = {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}

            # Build SOQL query
            query = "SELECT Id, Subject, Description, StartDateTime, EndDateTime, Location, OwnerId, WhatId, WhoId "
            query += "FROM Event "
            query += f"WHERE StartDateTime >= {start_datetime} AND EndDateTime <= {end_datetime} "

            # Add owner filter if specified
            if owner_id:
                query += f"AND OwnerId = '{owner_id}' "

            # Add user filter if specified (filter by WhoId for user appointments)
            if user_id:
                query += f"AND WhoId = '{user_id}' "

            query += "ORDER BY StartDateTime ASC "

            # URL encode the query
            encoded_query = urllib.parse.quote(query)
            self.logger.info(f"SOQL Query: {query}")

            # Create query URL
            url_query = f"{self._instance_url}/services/data/{self._version_api}/query/?q={encoded_query}"

            start_date_formated = start_datetime if "T" in start_datetime else f"{start_datetime}T"
            end_date_formated = end_datetime if "T" in end_datetime else f"{end_datetime}T"
            #
            if start_date_formated.endswith("T"):
                start_date_formated += "00:00:00"
            if end_date_formated.endswith("T"):
                end_date_formated += "23:59:59"
            #
            if not start_date_formated.endswith("Z"):
                start_date_formated += "Z"
            if not end_date_formated.endswith("Z"):
                end_date_formated += "Z"

            # Send request
            async with httpx.AsyncClient() as client:
                resp = await client.get(url_query, headers=headers)
                resp.raise_for_status()

                data = resp.json()
                local_tz = pytz.timezone("Europe/Paris")

                def convert_times(records):
                    processed_events = []
                    for event in records:
                        if event.get("StartDateTime"):
                            utc_dt = datetime.fromisoformat(event["StartDateTime"].replace("Z", "+00:00"))
                            event["StartDateTime"] = utc_dt.astimezone(local_tz).isoformat()
                        if event.get("EndDateTime"):
                            utc_dt = datetime.fromisoformat(event["EndDateTime"].replace("Z", "+00:00"))
                            event["EndDateTime"] = utc_dt.astimezone(local_tz).isoformat()
                        processed_events.append(event)
                    return processed_events

                events = convert_times(data.get("records", []))
                total_size = data.get("totalSize", 0)
                self.logger.info(f"Retrieved {total_size} events")

                # Handle pagination if needed
                next_records_url = data.get("nextRecordsUrl")
                while next_records_url:
                    next_url = f"{self._instance_url}{next_records_url}"
                    resp = await client.get(next_url, headers=headers)
                    resp.raise_for_status()

                    next_data = resp.json()
                    events.extend(convert_times(next_data.get("records", [])))
                    next_records_url = next_data.get("nextRecordsUrl")

                return events

        try:
            return await self._with_auth_retry(_execute_appointments_query)
        except httpx.HTTPStatusError as http_err:
            self.logger.info(f"Error retrieving events: {http_err.response.status_code}")
            try:
                self.logger.info(json.dumps(http_err.response.json(), indent=2, ensure_ascii=False))
            except Exception:
                self.logger.info(http_err.response.text)
            return []
        except Exception as e:
            self.logger.info(f"Error retrieving events: {e!s}")
            return []

    @measure_latency(OperationType.SALESFORCE, provider="salesforce")
    async def delete_event_by_id_async(self, event_id: str) -> bool:
        await self._ensure_authenticated_async()

        async def _execute_event_deletion():
            headers = {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}

            url_deletion_event = f"{self._instance_url}/services/data/{self._version_api}/sobjects/Event/{event_id}"

            async with httpx.AsyncClient() as client:
                resp_event = await client.delete(url_deletion_event, headers=headers)
                resp_event.raise_for_status()

                if resp_event.status_code == 204:
                    self.logger.info("Event deleted successfully!")
                    return True
                else:
                    self.logger.info(f"Unexpected status code while deleting the Event: {resp_event.status_code}")
                    return False

        try:
            return await self._with_auth_retry(_execute_event_deletion)
        except httpx.HTTPStatusError as http_err:
            self.logger.info(f"Error while deleting the Event: {http_err.response.status_code}")
            try:
                self.logger.info(json.dumps(http_err.response.json(), indent=2, ensure_ascii=False))
            except:
                self.logger.info(http_err.response.text)
            return False
        except Exception as e:
            self.logger.error(f"Error deleting event: {e!s}")
            return False

    @measure_latency(OperationType.SALESFORCE, provider="salesforce")
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

        async def _execute_person_search():
            headers = {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}

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
                url_contact_query = (
                    f"{self._instance_url}/services/data/{self._version_api}/query/?q={encoded_contact_query}"
                )

                try:
                    resp = await client.get(url_contact_query, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    records = data.get("records", [])
                    if records:
                        contact_data = records[0]
                        self.logger.info(
                            f"Found Contact: Id= {contact_data.get('Id')}, Name= {contact_data.get('FirstName')} {contact_data.get('LastName')}"
                        )
                        return {"type": "Contact", "data": contact_data}
                except httpx.HTTPStatusError as http_err:
                    self.logger.info(f"HTTP error querying Contact: {http_err} - Status: {http_err.response.status_code}")
                    try:
                        self.logger.info(json.dumps(http_err.response.json(), indent=2, ensure_ascii=False))
                    except json.JSONDecodeError:
                        self.logger.info(http_err.response.text)
                    raise http_err
                except httpx.RequestError as req_err:
                    self.logger.info(f"Request error querying Contact: {req_err!s}")
                    raise req_err
                except Exception as e:
                    self.logger.info(f"Generic exception querying Contact: {e!s}")
                    raise e

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
                    records = data.get("records", [])
                    if records:
                        lead_data = records[0]
                        self.logger.info(f"Found Lead: {lead_data.get('Id')} - {lead_data.get('FirstName')} {lead_data.get('LastName')}")
                        return {"type": "Lead", "data": lead_data}
                except httpx.HTTPStatusError as http_err:
                    self.logger.info(f"HTTP error querying Lead: {http_err} - Status: {http_err.response.status_code}")
                    try:
                        self.logger.info(json.dumps(http_err.response.json(), indent=2, ensure_ascii=False))
                    except json.JSONDecodeError:
                        self.logger.info(http_err.response.text)
                    raise http_err
                except httpx.RequestError as req_err:
                    self.logger.info(f"Request error querying Lead: {req_err!s}")
                    raise req_err
                except Exception as e:
                    self.logger.info(f"Generic exception querying Lead: {e!s}")
                    raise e

                self.logger.info(f"No Contact or non-converted Lead found for phone number: {phone_number}")
                return None

        try:
            return await self._with_auth_retry(_execute_person_search)
        except (httpx.RequestError, Exception) as e:
            self.logger.info(f"Error searching for person with phone {phone_number}: {e!s}")
            return None

    async def get_persons_async(self) -> list[dict]:
        """
        Retrieve lestest Contacts and Leads from Salesforce (asynchronous).

        Returns:
            A list of dictionaries containing the person's type ('Contact' or 'Lead') and data.
        """
        await self._ensure_authenticated_async()
        headers = {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}

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
            url_contact_query = (
                f"{self._instance_url}/services/data/{self._version_api}/query/?q={encoded_contact_query}"
            )

            try:
                resp = await client.get(url_contact_query, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                records = data.get("records", [])
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
                self.logger.error(f"Request error querying Contact: {req_err!s}")
            except Exception as e:
                self.logger.error(f"Generic exception querying Contact: {e!s}")

            return None

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
        await self._ensure_authenticated_async()

        headers = {"Authorization": f"Bearer {self._access_token}"}
        schema = {}

        async def _fetch_sobjects_list():
            async with httpx.AsyncClient() as client:
                all_sobjects_url = f"{self._instance_url}/services/data/{self._version_api}/sobjects/"
                self.logger.info("Fetching list of all SObjects...")
                resp = await client.get(all_sobjects_url, headers=headers)
                resp.raise_for_status()
                return resp.json()

        try:
            all_sobjects_data = await self._with_auth_retry(_fetch_sobjects_list)
        except httpx.HTTPStatusError as http_err_main:
            self.logger.error(f"HTTP error getting SObject list: {http_err_main} - Status: {http_err_main.response.status_code}")
            try:
                self.logger.error(json.dumps(http_err_main.response.json(), indent=2))
            except:
                self.logger.error(http_err_main.response.text)
            return None
        except Exception as e_main:
            self.logger.error(f"Error fetching SObject list: {e_main!s}")
            return None

        # Determine the list of SObjects to describe
        target_sobjects_info = []
        all_sobjects_metadata_list = all_sobjects_data.get("sobjects", [])

        if sobjects_to_describe:
            s_name_to_url_map = {
                s_info["name"]: s_info["urls"]["describe"]
                for s_info in all_sobjects_metadata_list
                if "name" in s_info and "urls" in s_info and "describe" in s_info["urls"]
            }
            for s_name in sobjects_to_describe:
                if s_name in s_name_to_url_map:
                    target_sobjects_info.append({"name": s_name, "describe_url_path": s_name_to_url_map[s_name]})
                else:  # Fallback to constructing the URL if not found (e.g. object not in global list, or list was partial)
                    target_sobjects_info.append({
                        "name": s_name,
                        "describe_url_path": f"/services/data/{self._version_api}/sobjects/{s_name}/describe/",
                    })
            self.logger.info(
                f"Will describe {len(target_sobjects_info)} specified SObjects: {', '.join(s_name for s_name in sobjects_to_describe)}"
            )
        else:
            target_sobjects_info = [
                {"name": s_info["name"], "describe_url_path": s_info["urls"]["describe"]}
                for s_info in all_sobjects_metadata_list
                if "name" in s_info and "urls" in s_info and "describe" in s_info["urls"]
            ]
            self.logger.info(
                f"Found {len(target_sobjects_info)} SObjects. Describing all can be very slow and consume many API calls."
            )

        total_objects_to_describe = len(target_sobjects_info)
        for i, sobject_item in enumerate(target_sobjects_info):
            s_name = sobject_item["name"]
            describe_url = f"{self._instance_url}{sobject_item['describe_url_path']}"

            self.logger.info(f"Describing SObject {i + 1}/{total_objects_to_describe}: {s_name}...")

            async def _describe_sobject():
                async with httpx.AsyncClient() as client:
                    desc_resp = await client.get(describe_url, headers=headers)
                    desc_resp.raise_for_status()
                    return desc_resp.json()

            try:
                s_description = await self._with_auth_retry(_describe_sobject)

                fields_info = {}
                for field in s_description.get("fields", []):
                    field_name = field.get("name")
                    is_pk = field_name == "Id"
                    is_fk = field.get("type") == "reference" and bool(field.get("referenceTo"))

                    if include_fields or is_pk or is_fk:
                        fields_info[field_name] = {
                            "label": field.get("label"),
                            "type": field.get("type"),
                            "length": field.get("length", 0)
                            if field.get("type")
                            in [
                                "string",
                                "textarea",
                                "phone",
                                "url",
                                "email",
                                "picklist",
                                "multipicklist",
                                "combobox",
                                "id",
                                "reference",
                            ]
                            else None,
                            "precision": field.get("precision")
                            if field.get("type") in ["currency", "double", "percent", "int", "long"]
                            else None,
                            "scale": field.get("scale")
                            if field.get("type") in ["currency", "double", "percent"]
                            else None,
                            "nillable": field.get("nillable"),
                            "custom": field.get("custom"),
                            "is_primary_key": is_pk,
                            "is_foreign_key": is_fk,
                            "references_to": field.get("referenceTo", []) if is_fk else [],
                        }
                schema[s_name] = {"fields": fields_info}

                # Brief pause to avoid hitting rate limits too hard
                if total_objects_to_describe > 10 and i < total_objects_to_describe - 1:
                    await asyncio.sleep(0.2)  # 200ms delay

            except httpx.HTTPStatusError as http_err_desc:
                error_detail = "Unknown error"
                try:
                    error_detail = json.dumps(http_err_desc.response.json(), indent=2)
                except:
                    error_detail = http_err_desc.response.text
                self.logger.info(
                    f"HTTP error describing SObject {s_name}: {http_err_desc} - Status: {http_err_desc.response.status_code}. Details: {error_detail[:500]}"
                )
                schema[s_name] = {"error": f"Failed to describe: {http_err_desc!s}"}
            except Exception as e_desc:
                self.logger.info(f"Error describing SObject {s_name}: {e_desc!s}")
                schema[s_name] = {"error": f"Failed to describe: {e_desc!s}"}

        return schema

    async def _with_auth_retry(self, func, *args, **kwargs):
        """
        Execute an async function with automatic 401 retry logic.
        If the function raises a 401 HTTPStatusError, re-authenticate and retry once.

        Args:
            func: The async function to execute
            *args: Positional arguments to pass to func
            **kwargs: Keyword arguments to pass to func

        Returns:
            The result of the function call

        Raises:
            The original exception if retry fails or if error is not 401
        """
        try:
            return await func(*args, **kwargs)
        except httpx.HTTPStatusError as http_err:
            if http_err.response.status_code == 401:
                self.logger.info("Received 401 authentication error, attempting to re-authenticate and retry...")

                # Re-authenticate
                if self.authenticate():
                    self.logger.info("Re-authentication successful, retrying original request...")
                    try:
                        return await func(*args, **kwargs)
                    except Exception as retry_err:
                        self.logger.error(f"Retry after re-authentication failed: {retry_err!s}")
                        raise retry_err
                else:
                    self.logger.error("Re-authentication failed, cannot retry request")
                    raise http_err
            else:
                # Not a 401 error, re-raise original exception
                raise http_err

    async def _create_opportunity_contact_role(
        self,
        opportunity_id: str,
        contact_id: str,
        role: str,
        client: httpx.AsyncClient,
        headers: dict
    ) -> bool:
        """
        Internal helper to create an OpportunityContactRole.

        Args:
            opportunity_id: ID of the Opportunity
            contact_id: ID of the Contact
            role: Role of the contact (e.g., "Decision Maker", "Influencer", "Economic Buyer")
            client: HTTP client instance
            headers: HTTP headers for the request

        Returns:
            True if successful, False otherwise
        """
        try:
            # Prepare OpportunityContactRole payload
            role_payload = {
                "OpportunityId": opportunity_id,
                "ContactId": contact_id,
                "Role": role,
                "IsPrimary": True  # Mark as primary contact for this opportunity
            }

            url_create_role = f"{self._instance_url}/services/data/{self._version_api}/sobjects/OpportunityContactRole/"

            resp = await client.post(url_create_role, headers=headers, json=role_payload)
            resp.raise_for_status()

            role_data = resp.json()
            role_id = role_data.get("id")

            if role_id:
                self.logger.info(f"OpportunityContactRole created successfully! Role ID: {role_id}")
                return True
            else:
                self.logger.error("OpportunityContactRole creation failed - no ID returned")
                return False

        except httpx.HTTPStatusError as http_err:
            self.logger.error(f"Error creating OpportunityContactRole: {http_err.response.status_code}")
            try:
                self.logger.error(json.dumps(http_err.response.json(), indent=2, ensure_ascii=False))
            except Exception:
                self.logger.error(http_err.response.text)
            return False
        except Exception as e:
            self.logger.error(f"Error creating OpportunityContactRole: {e!s}")
            return False

    @measure_latency(OperationType.SALESFORCE, provider="salesforce")
    async def add_contact_role_to_opportunity_async(
        self,
        opportunity_id: str,
        contact_id: str,
        role: str = "Decision Maker",
        is_primary: bool = False
    ) -> str | None:
        """
        Add a Contact role to an existing Opportunity by creating an OpportunityContactRole.

        Args:
            opportunity_id: ID of the Opportunity (required)
            contact_id: ID of the Contact (required)
            role: Role of the contact (default: "Decision Maker")
                  Common values: "Decision Maker", "Economic Buyer", "Economic Decision Maker",
                  "Technical Buyer", "Influencer", "User", "Other"
            is_primary: Whether this should be the primary contact for the opportunity

        Returns:
            The ID of the created OpportunityContactRole if successful, None otherwise
        """
        await self._ensure_authenticated_async()

        if not opportunity_id or not contact_id:
            self.logger.error("Error: opportunity_id and contact_id are required")
            return None

        self.logger.info(f"Adding Contact {contact_id} to Opportunity {opportunity_id} with role: {role}")

        async def _execute_role_creation():
            headers = {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}

            # Prepare OpportunityContactRole payload
            role_payload = {
                "OpportunityId": opportunity_id,
                "ContactId": contact_id,
                "Role": role,
                "IsPrimary": is_primary
            }

            url_create_role = f"{self._instance_url}/services/data/{self._version_api}/sobjects/OpportunityContactRole/"

            async with httpx.AsyncClient() as client:
                resp = await client.post(url_create_role, headers=headers, json=role_payload)
                resp.raise_for_status()

                role_data = resp.json()
                role_id = role_data.get("id")

                if role_id:
                    self.logger.info("OpportunityContactRole created successfully!")
                    self.logger.info(f"Role ID: {role_id}")
                    return role_id
                else:
                    self.logger.error("OpportunityContactRole creation failed - no ID returned")
                    return None

        try:
            return await self._with_auth_retry(_execute_role_creation)
        except httpx.HTTPStatusError as http_err:
            self.logger.error(f"Error creating OpportunityContactRole: {http_err.response.status_code}")
            try:
                self.logger.error(json.dumps(http_err.response.json(), indent=2, ensure_ascii=False))
            except Exception:
                self.logger.error(http_err.response.text)
            return None
        except Exception as e:
            self.logger.error(f"Error creating OpportunityContactRole: {e!s}")
            return None

    ## Internal helpers ##

    def _get_french_datetime_from_str(self, datetime_str: str) -> datetime | None:
        pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
        if not re.match(pattern, datetime_str):
            self.logger.info(f"Invalid 'datetime_str' paramter format: {datetime_str}")
            self.logger.info("datetime_str must be in the format 'YYYY-MM-DDTHH:MM:SSZ', like: '2025-06-15T23:59:59Z'")
            return None
        start_dt = datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%SZ")
        start_dt_utc = start_dt.replace(tzinfo=pytz.utc)
        french_tz = pytz.timezone("Europe/Paris")
        return start_dt_utc.astimezone(french_tz)

    def _get_str_from_datetime(self, dt: datetime) -> str:
        """Convert a datetime to a string in the format 'YYYY-MM-DDTHH:MM:SSZ'"""
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _to_utc_datetime(self, dt: datetime) -> datetime:
        """Convert a naive or local-aware datetime to UTC-aware datetime."""
        if dt.tzinfo is None:
            # Assume naive datetimes are in local time; convert to UTC
            return dt.astimezone(UTC)
        return dt.astimezone(UTC)

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

        async def _execute_query():
            headers = {"Authorization": f"Bearer {self._access_token}"}
            encoded_query = urllib.parse.quote(soql_query)
            url_query = f"{self._instance_url}/services/data/{self._version_api}/query/?q={encoded_query}"

            # self.logger.info(f"Executing SOQL: {soql_query}") # Verbose, enable for deep debugging
            async with httpx.AsyncClient() as client:
                resp = await client.get(url_query, headers=headers)
                resp.raise_for_status()  # Will raise HTTPStatusError for 4xx/5xx status codes
                return resp.json()

        try:
            return await self._with_auth_retry(_execute_query)
        except httpx.HTTPStatusError as http_err:
            error_message = (
                f"SOQL Query HTTP error: {http_err} - Status: {http_err.response.status_code}. Query: {soql_query}"
            )
            self.logger.info(error_message)
            try:
                error_details = http_err.response.json()
                self.logger.info(json.dumps(error_details, indent=2, ensure_ascii=False))
            except json.JSONDecodeError:
                self.logger.info(f"Response text: {http_err.response.text}")
            return None
        except Exception as e:
            self.logger.info(f"SOQL Query general error: {e!s}. Query: {soql_query}")
            return None

    async def get_leads_by_details_async(
        self,
        email: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        company_name: str | None = None,
    ) -> list[dict] | None:
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
            self.logger.info(
                "Warning: For name-based Lead search, providing both first_name and last_name is recommended for accuracy."
            )
            if first_name:
                conditions.append(f"FirstName = '{first_name}'")
            if last_name:
                conditions.append(f"LastName = '{last_name}'")
        if company_name:
            conditions.append(f"Company = '{company_name}'")

        if len(conditions) == 1:  # Only IsConverted = false, no other criteria
            self.logger.info(
                "Error: At least one search criterion (email, full name, or company) must be provided for get_leads_by_details_async."
            )
            return None  # Or an empty list if that's preferred for bad input

        query_filter = " AND " + " AND ".join(f"({c})" for c in conditions[1:])

        soql_query = (
            "SELECT Id, FirstName, LastName, Email, Company, Status, Owner.Name, CreatedDate "
            "FROM Lead "
            f"WHERE {conditions[0]} {query_filter} "
            "ORDER BY CreatedDate DESC LIMIT 200"  # Added LIMIT for safety
        )

        response_data = await self._query_salesforce(soql_query)
        if response_data and response_data.get("records") is not None:
            return response_data["records"]
        elif response_data is None:  # Error occurred in _query_salesforce
            return None
        else:  # Query successful, but no records found (e.g. response_data['records'] is empty list)
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
        lead_info_soql = (
            f"SELECT Id, IsConverted, ConvertedOpportunityId, ConvertedAccountId FROM Lead WHERE Id = '{lead_id}'"
        )
        lead_response = await self._query_salesforce(lead_info_soql)

        if not lead_response or lead_response.get("records") is None:
            # _query_salesforce would have printed an error if lead_response is None
            # If records is None (but lead_response isn't), or empty, Lead not found or query issue.
            if lead_response and lead_response.get("totalSize", 0) == 0:
                self.logger.info(f"Lead with ID '{lead_id}' not found.")
                return []
            return None  # Error occurred during query

        lead_data = lead_response["records"][0]
        is_converted = lead_data.get("IsConverted")
        converted_opp_id = lead_data.get("ConvertedOpportunityId")
        converted_acc_id = lead_data.get("ConvertedAccountId")

        opportunity_soql = ""
        common_opp_fields = "SELECT Id, Name, StageName, Amount, CloseDate, AccountId, Account.Name, Owner.Name, CreatedDate FROM Opportunity"

        if is_converted and converted_opp_id:
            self.logger.info(
                f"Lead '{lead_id}' was converted to Opportunity ID: '{converted_opp_id}'. Fetching this Opportunity."
            )
            opportunity_soql = f"{common_opp_fields} WHERE Id = '{converted_opp_id}' LIMIT 1"
        elif is_converted and converted_acc_id:
            self.logger.info(
                f"Lead '{lead_id}' was converted to Account ID: '{converted_acc_id}'. Searching Opportunities for this Account."
            )
            opportunity_soql = (
                f"{common_opp_fields} WHERE AccountId = '{converted_acc_id}' ORDER BY CreatedDate DESC LIMIT 200"
            )
        else:
            self.logger.info(
                f"Lead '{lead_id}' is not converted, or no ConvertedOpportunityId/ConvertedAccountId found. No direct Opportunities from conversion."
            )
            return []

        if not opportunity_soql:  # Should not happen if logic above is correct, but as a safeguard.
            return []

        opp_response = await self._query_salesforce(opportunity_soql)
        if opp_response and opp_response.get("records") is not None:
            return opp_response["records"]
        elif opp_response is None:  # Error in _query_salesforce
            return None
        else:  # Query successful, but no records (e.g. opp_response['records'] is empty list)
            return []

    @measure_latency(OperationType.SALESFORCE, provider="salesforce")
    async def get_opportunities_by_contact_async(self, contact_id: str) -> list[dict] | None:
        """
        Retrieve Opportunities related to a specific Contact via Account relationship (asynchronous).
        
        Args:
            contact_id: The ID of the Salesforce Contact.
            
        Returns:
            A list of Opportunity dictionaries related to the contact's account. 
            Returns None on error, empty list if no related opportunities found.
        """
        await self._ensure_authenticated_async()

        if not contact_id:
            self.logger.info("Error: contact_id must be provided.")
            return None

        # Step 1: Get Contact's Account information
        contact_info_soql = f"SELECT Id, AccountId, Account.Id FROM Contact WHERE Id = '{contact_id}'"
        contact_response = await self._query_salesforce(contact_info_soql)

        if not contact_response or contact_response.get("records") is None:
            if contact_response and contact_response.get("totalSize", 0) == 0:
                self.logger.info(f"Contact with ID '{contact_id}' not found.")
                return []
            return None  # Error occurred during query

        contact_data = contact_response["records"]
        account_id = contact_data[0].get("AccountId") if any(contact_data) else None

        if not account_id:
            self.logger.info(f"Contact '{contact_id}' has no associated Account. No opportunities can be retrieved.")
            return []

        # Step 2: Get Opportunities for the Account
        self.logger.info(f"Contact '{contact_id}' is linked to Account '{account_id}'. Searching Opportunities for this Account.")
        
        opportunity_soql = (
            "SELECT Id, Name, StageName, Amount, CloseDate, AccountId, Account.Name, OwnerId, Owner.Name, CreatedDate "
            "FROM Opportunity "
            f"WHERE AccountId = '{account_id}' "
            "ORDER BY CreatedDate DESC LIMIT 200"
        )

        opp_response = await self._query_salesforce(opportunity_soql)
        if opp_response and opp_response.get("records") is not None:
            opportunities = opp_response["records"]
            self.logger.info(f"Found {len(opportunities)} opportunities for Contact '{contact_id}' via Account '{account_id}'")
            return opportunities
        elif opp_response is None:  # Error in _query_salesforce
            return None
        else:  # Query successful, but no records
            return []

    @measure_latency(OperationType.SALESFORCE, provider="salesforce")
    async def get_user_by_id_async(self, user_id: str) -> dict | None:
        """
        Retrieve detailed information about a Salesforce User by ID (asynchronous).
        
        Args:
            user_id: The ID of the Salesforce User.
            
        Returns:
            A dictionary containing user information, or None if user not found or error occurs.
        """
        await self._ensure_authenticated_async()

        if not user_id:
            self.logger.info("Error: user_id must be provided.")
            return None

        user_soql = (
            "SELECT Id, Name, FirstName, LastName, Email, Phone, Title, Department, IsActive, CreatedDate "
            "FROM User "
            f"WHERE Id = '{user_id}' "
            "LIMIT 1"
        )

        self.logger.info(f"Retrieving user information for ID: {user_id}")
        
        user_response = await self._query_salesforce(user_soql)
        if user_response and user_response.get("records") is not None:
            users = user_response["records"]
            if users:
                user_data = users[0]
                self.logger.info(f"Found user: {user_data.get('Name')} ({user_data.get('Email')})")
                return user_data
            else:
                self.logger.info(f"User with ID '{user_id}' not found.")
                return None
        elif user_response is None:  # Error in _query_salesforce
            return None
        else:  # Query successful, but no records
            self.logger.info(f"User with ID '{user_id}' not found.")
            return None

    def _get_owner_by_strategy(
        self, 
        person_type: str, 
        contact_info: dict, 
        opportunities: list | None, 
        strategy: str
    ) -> tuple[str | None, str | None]:
        """
        Centralized logic for owner (CF) retrieval based on strategy.
        
        Args:
            person_type: "Contact" or "Lead"
            contact_info: Contact/Lead data dictionary
            opportunities: List of opportunities (can be None or empty)
            strategy: Owner retrieval strategy ("both", "opport_only", "direct_only")
            
        Returns:
            tuple[str | None, str | None]: (user_id, user_source)
        """
        user_id = None
        user_source = None
        
        # Strategy: direct_only - Always use contact/lead owner, skip opportunities
        if strategy == "direct_only":
            if contact_info.get("Owner", {}).get("Id"):
                user_id = contact_info.get("Owner", {}).get("Id")
                user_source = person_type.lower()
                self.logger.info(f"Strategy 'direct_only': Using {person_type.lower()} owner: {user_id}")
            return user_id, user_source
            
        # Strategy: opport_only - Only use opportunity owner, no fallback
        elif strategy == "opport_only":
            if opportunities:
                most_recent_opportunity = opportunities[0]
                if person_type == "Contact":
                    # For contacts, OwnerId is directly on the opportunity
                    if most_recent_opportunity.get("OwnerId"):
                        user_id = most_recent_opportunity.get("OwnerId")
                        user_source = "opportunity"
                        self.logger.info(f"Strategy 'opport_only': Using opportunity owner: {user_id}")
                elif person_type == "Lead":
                    # For leads, Owner information is nested
                    if most_recent_opportunity.get("Owner", {}).get("Id"):
                        user_id = most_recent_opportunity.get("Owner", {}).get("Id")
                        user_source = "opportunity"
                        self.logger.info(f"Strategy 'opport_only': Using opportunity owner: {user_id}")
            if not user_id:
                self.logger.info(f"Strategy 'opport_only': No opportunity owner found, no fallback")
            return user_id, user_source
            
        # Strategy: both (default) - Try opportunity first, fallback to contact/lead owner
        elif strategy == "both":
            # First try to get user from most recent opportunity
            if opportunities:
                most_recent_opportunity = opportunities[0]
                if person_type == "Contact":
                    if most_recent_opportunity.get("OwnerId"):
                        user_id = most_recent_opportunity.get("OwnerId")
                        user_source = "opportunity"
                        self.logger.info(f"Strategy 'both': Using opportunity owner: {user_id}")
                elif person_type == "Lead":
                    if most_recent_opportunity.get("Owner", {}).get("Id"):
                        user_id = most_recent_opportunity.get("Owner", {}).get("Id")
                        user_source = "opportunity"
                        self.logger.info(f"Strategy 'both': Using opportunity owner: {user_id}")
            
            # Fallback to contact/lead owner if no opportunity owner found
            if not user_id and contact_info.get("Owner", {}).get("Id"):
                user_id = contact_info.get("Owner", {}).get("Id")
                user_source = person_type.lower()
                self.logger.info(f"Strategy 'both': Fallback to {person_type.lower()} owner: {user_id}")
                
            return user_id, user_source
        else:
            return None, None

    @measure_latency(OperationType.SALESFORCE, provider="salesforce")
    async def get_complete_contact_info_by_phone_async(self, phone_number: str) -> dict | None:
        """
        Aggregated method to retrieve complete contact information from a phone number.
        
        This method combines multiple sub-methods:
        1. Search for contact by phone number
        2. Get opportunities related to the contact (based on strategy)
        3. Get the most recent opportunity
        4. Get user associated with the opportunity or contact (based on strategy)
        
        Args:
            phone_number: The phone number to search for.
            
        Returns:
            A dictionary containing contact, opportunities, and user information,
            or None if no contact found or error occurs.
        """
        if not phone_number:
            self.logger.info("Error: phone_number must be provided.")
            return None

        # Get the owner retrieval strategy from environment
        strategy = EnvHelper.get_salesforce_owner_strategy()
        self.logger.info(f"Starting complete contact info retrieval for phone number: {phone_number} with strategy: {strategy}")

        # Step 1: Search for contact by phone number
        person_data = await self.get_person_by_phone_async(phone_number)
        if not person_data:
            self.logger.info(f"No contact or lead found for phone number: {phone_number}")
            return None

        person_type = person_data.get("type")
        contact_info = person_data.get("data")
        
        result = {
            "contact": contact_info,
            "contact_type": person_type,
            "opportunities": [],
            "most_recent_opportunity": None,
            "assigned_user": None,
            "user_source": None
        }

        # Handle different contact types
        if person_type == "Contact":
            contact_id = contact_info.get("Id")
            
            # Step 2: Get opportunities related to the contact (based on strategy)
            opportunities = []
            if strategy != "direct_only":
                self.logger.info(f"Retrieving opportunities for Contact ID: {contact_id}")
                opportunities = await self.get_opportunities_by_contact_async(contact_id)
                
                if opportunities is None:
                    self.logger.warning("Error occurred while retrieving opportunities, but continuing with contact info")
                    opportunities = []
            else:
                self.logger.info("Strategy 'direct_only': Skipping opportunity retrieval")
            
            result["opportunities"] = opportunities

            # Step 3: Get the most recent opportunity
            most_recent_opportunity = None
            if opportunities:
                most_recent_opportunity = opportunities[0]  # Already sorted by CreatedDate DESC
                result["most_recent_opportunity"] = most_recent_opportunity
                self.logger.info(f"Found {len(opportunities)} opportunities, most recent: {most_recent_opportunity.get('Name')}")

            # Step 4: Get user information using strategy
            user_id, user_source = self._get_owner_by_strategy(person_type, contact_info, opportunities, strategy)

            # Step 5: Retrieve user information
            if user_id:
                user_info = await self.get_user_by_id_async(user_id)
                if user_info:
                    result["assigned_user"] = user_info
                    result["user_source"] = user_source
                    self.logger.info(f"Successfully retrieved user info for {user_info.get('Name')} (source: {user_source})")
                else:
                    self.logger.warning(f"Could not retrieve user information for ID: {user_id}")
            else:
                self.logger.info(f"No user ID available for strategy '{strategy}'")

        elif person_type == "Lead":
            # For Leads, we can try to get opportunities if it's converted (based on strategy)
            lead_id = contact_info.get("Id")
            opportunities = []
            
            if strategy != "direct_only":
                self.logger.info(f"Found Lead ID: {lead_id}, checking for converted opportunities")
                # Use existing method for lead opportunities
                opportunities = await self.get_opportunities_for_lead_async(lead_id)
                
                if opportunities is None:
                    self.logger.warning("Error occurred while retrieving opportunities for lead, but continuing with lead info")
                    opportunities = []
            else:
                self.logger.info("Strategy 'direct_only': Skipping opportunity retrieval for lead")
            
            result["opportunities"] = opportunities

            # Get most recent opportunity if any
            most_recent_opportunity = None
            if opportunities:
                most_recent_opportunity = opportunities[0]  # Already sorted by CreatedDate DESC
                result["most_recent_opportunity"] = most_recent_opportunity
                self.logger.info(f"Found {len(opportunities)} opportunities for lead, most recent: {most_recent_opportunity.get('Name')}")

            # Get user information using strategy
            user_id, user_source = self._get_owner_by_strategy(person_type, contact_info, opportunities, strategy)

            # Retrieve user information
            if user_id:
                user_info = await self.get_user_by_id_async(user_id)
                if user_info:
                    result["assigned_user"] = user_info
                    result["user_source"] = user_source
                    self.logger.info(f"Successfully retrieved user info for {user_info.get('Name')} (source: {user_source})")
                else:
                    self.logger.warning(f"Could not retrieve user information for ID: {user_id}")
            else:
                self.logger.info(f"No user ID available for strategy '{strategy}'")

        self.logger.info(f"Complete contact info retrieval finished for {phone_number}. Found {len(result['opportunities'])} opportunities.")
        return result

    @measure_latency(OperationType.SALESFORCE, provider="salesforce")
    async def get_appointment_slots_with_lightning_scheduler_async(
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
            work_type_id: Work Type ID for the appointment (optional, uses default from env)
            service_territory_id: Service Territory ID (optional, uses default from env)
            
        Returns:
            List of available appointment slots if successful, None otherwise
        """
        await self._ensure_authenticated_async()

        # Use defaults from environment if not provided
        work_type_id = work_type_id or EnvHelper.get_salesforce_default_work_type_id()
        service_territory_id = service_territory_id or EnvHelper.get_salesforce_default_service_territory_id()

        if not work_type_id or not service_territory_id:
            self.logger.error("Error: work_type_id and service_territory_id are required for Lightning Scheduler")
            return None

        async def _execute_get_appointment_slots():
            headers = {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}

            # Prepare request payload for Lightning Scheduler API
            payload = {
                "startTime": start_datetime,
                "endTime": end_datetime,
                "workTypeId": work_type_id,
                "serviceTerritoryId": service_territory_id,
                "allowConcurrentAppointments": False
            }

            url_scheduler_api = f"{self._instance_url}/services/data/{self._version_api}/lightning/scheduler-api/getAppointmentSlots"
            self.logger.debug(f"Lightning Scheduler API URL: {url_scheduler_api}")
            self.logger.debug(f"Request payload: {payload}")

            async with httpx.AsyncClient() as client:
                resp = await client.post(url_scheduler_api, headers=headers, json=payload)
                resp.raise_for_status()
                
                data = resp.json()
                available_slots = data.get("slots", [])
                
                self.logger.info(f"Found {len(available_slots)} available appointment slots")
                return available_slots

        try:
            return await self._with_auth_retry(_execute_get_appointment_slots)
        except httpx.HTTPStatusError as http_err:
            self.logger.error(f"Error retrieving appointment slots: {http_err.response.status_code}")
            try:
                self.logger.error(json.dumps(http_err.response.json(), indent=2, ensure_ascii=False))
            except Exception:
                self.logger.error(http_err.response.text)
            return None
        except Exception as e:
            self.logger.error(f"Error retrieving appointment slots: {e!s}")
            return None

    @measure_latency(OperationType.SALESFORCE, provider="salesforce")
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
            work_type_id: Work Type ID (optional, uses default from env)
            service_territory_id: Service Territory ID (optional, uses default from env) 
            parent_record_id: Parent record ID (Work Order, etc.)
            max_retries: Maximum number of retry attempts if verification fails
            retry_delay: Delay in seconds before retry attempt
            
        Returns:
            The ID of the created ServiceAppointment if successful, None otherwise
        """
        await self._ensure_authenticated_async()
        
        if not subject or not start_datetime:
            self.logger.error("Error: Required appointment fields (subject, start_datetime) are missing")
            return None

        # Validate retry parameters
        if max_retries < 0:
            max_retries = 0
        if retry_delay < 0:
            retry_delay = 0

        # Use defaults from environment if not provided
        work_type_id = work_type_id or EnvHelper.get_salesforce_default_work_type_id()
        service_territory_id = service_territory_id or EnvHelper.get_salesforce_default_service_territory_id()

        if not work_type_id or not service_territory_id:
            self.logger.error("Error: work_type_id and service_territory_id are required for Lightning Scheduler")
            return None

        # Convert to UTC and calculate end time
        start_dt = self._get_french_datetime_from_str(start_datetime)
        if start_dt is None:
            self.logger.error("Error: Invalid start_datetime format")
            return None

        # Apply timezone offset for docker container issue
        french_now = datetime.now(pytz.timezone("Europe/Paris"))
        utc_offset_hours = (french_now.utcoffset().total_seconds() or 0) / 3600
        if utc_offset_hours != 0:
            start_dt = start_dt - timedelta(hours=utc_offset_hours)
            self.logger.debug(f"UTC offset hours removed: {utc_offset_hours}")

        start_datetime_utc = self._to_utc_datetime(start_dt)
        end_datetime_utc = self._calculate_end_datetime(start_datetime_utc, duration_minutes)

        if not end_datetime_utc:
            self.logger.error("Error: Invalid start_datetime or duration_minutes")
            return None

        if start_datetime_utc <= datetime.now(UTC):
            self.logger.error("Error: Start datetime must be in the future")
            return None

        # Convert to string format for API calls
        start_datetime_str = self._get_str_from_datetime(start_datetime_utc)
        end_datetime_str = self._get_str_from_datetime(end_datetime_utc)

        # Verify slot availability before creating appointment
        self.logger.info("Verifying slot availability with Lightning Scheduler...")
        
        # Create a search window around the requested time (±15 minutes)
        search_start_time = start_datetime_utc - timedelta(minutes=15)
        search_end_time = end_datetime_utc + timedelta(minutes=15)
        search_start_str = self._get_str_from_datetime(search_start_time)
        search_end_str = self._get_str_from_datetime(search_end_time)
        
        available_slots = await self.get_appointment_slots_with_lightning_scheduler_async(
            start_datetime=search_start_str,
            end_datetime=search_end_str,
            work_type_id=work_type_id,
            service_territory_id=service_territory_id
        )
        
        if available_slots is None:
            self.logger.error("Error: Could not verify slot availability - proceeding with caution")
        elif not available_slots:
            self.logger.warning("Warning: No available slots found in the requested time window - proceeding anyway")
        else:
            # Check if any slot overlaps with our requested time
            slot_available = False
            for slot in available_slots:
                slot_start = slot.get('startTime', slot.get('Start', ''))
                slot_end = slot.get('endTime', slot.get('End', ''))
                
                if slot_start and slot_end:
                    # Parse slot times for comparison
                    try:
                        slot_start_dt = datetime.fromisoformat(slot_start.replace('Z', '+00:00')).replace(tzinfo=UTC)
                        slot_end_dt = datetime.fromisoformat(slot_end.replace('Z', '+00:00')).replace(tzinfo=UTC)
                        
                        # Check if requested appointment fits within any available slot
                        if (slot_start_dt <= start_datetime_utc and 
                            slot_end_dt >= end_datetime_utc):
                            slot_available = True
                            self.logger.info(f"✓ Slot verified: Available from {slot_start} to {slot_end}")
                            break
                    except (ValueError, TypeError) as e:
                        self.logger.debug(f"Could not parse slot time: {e}")
                        continue
            
            if not slot_available:
                self.logger.warning("Warning: Requested time slot may not be available - proceeding anyway")
            else:
                self.logger.info("✓ Slot availability confirmed")

        self.logger.info("Creating ServiceAppointment with Lightning Scheduler...")
        self.logger.debug(f"Start: {start_datetime_str}, End: {end_datetime_str}")

        async def _execute_appointment_creation():
            headers = {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}

            # Prepare ServiceAppointment payload
            service_appointment_payload = {
                "Subject": subject,
                "Status": "Scheduled",
                "SchedStartTime": start_datetime_str,
                "SchedEndTime": end_datetime_str,
                "ServiceTerritoryId": service_territory_id,
                "WorkTypeId": work_type_id
            }

            # Add optional fields
            if description:
                service_appointment_payload["Description"] = description
            if contact_id:
                service_appointment_payload["ContactId"] = contact_id
            if parent_record_id:
                service_appointment_payload["ParentRecordId"] = parent_record_id

            # Create ServiceAppointment using standard REST API
            url_create_appointment = f"{self._instance_url}/services/data/{self._version_api}/sobjects/ServiceAppointment/"
            
            async with httpx.AsyncClient() as client:
                resp = await client.post(url_create_appointment, headers=headers, json=service_appointment_payload)
                resp.raise_for_status()

                appointment_data = resp.json()
                appointment_id = appointment_data.get("id")
                
                if appointment_id:
                    self.logger.info("ServiceAppointment created successfully!")
                    self.logger.info(f"Appointment ID: {appointment_id}")
                    self.logger.info(f"View URL: {self._instance_url}/lightning/r/ServiceAppointment/{appointment_id}/view")
                    return appointment_id
                else:
                    self.logger.error("ServiceAppointment creation failed - no ID returned")
                    return None

        appointment_id = None
        creation_failed = False

        try:
            appointment_id = await self._with_auth_retry(_execute_appointment_creation)
        except httpx.HTTPStatusError as http_err:
            self.logger.error(f"Error creating ServiceAppointment: {http_err.response.status_code}")
            try:
                self.logger.error(json.dumps(http_err.response.json(), indent=2, ensure_ascii=False))
            except Exception:
                self.logger.error(http_err.response.text)
            creation_failed = True
        except Exception as e:
            self.logger.error(f"Error creating ServiceAppointment: {e!s}")
            creation_failed = True

        if not appointment_id:
            if creation_failed and max_retries > 0:
                self.logger.info(f"Creation failed, retrying in {retry_delay}s... ({max_retries} retries remaining)")
                await asyncio.sleep(retry_delay)

                # Recursive retry
                return await self.schedule_new_appointment_with_lightning_scheduler_async(
                    subject=subject,
                    start_datetime=start_datetime,
                    duration_minutes=duration_minutes,
                    description=description,
                    contact_id=contact_id,
                    work_type_id=work_type_id,
                    service_territory_id=service_territory_id,
                    parent_record_id=parent_record_id,
                    max_retries=max_retries - 1,
                    retry_delay=retry_delay,
                )
            else:
                self.logger.error("ServiceAppointment creation failed after all retry attempts")

        return appointment_id

    async def get_phone_numbers_async(self, limit: int = 10) -> list[dict] | None:
        """
        Retrieve the first x phone numbers from both Contacts and Leads in Salesforce.

        Args:
            limit: Number of phone numbers to retrieve (default: 10)

        Returns:
            A list of dictionaries containing phone numbers and associated person data,
            or None if an error occurs.
        """
        await self._ensure_authenticated_async()

        if limit <= 0:
            self.logger.info("Error: limit must be greater than 0")
            return None

        async def _execute_phone_numbers_search():
            headers = {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}
            phone_numbers = []

            async with httpx.AsyncClient() as client:
                # Get phone numbers from Contacts first
                contact_query = (
                    "SELECT Id, FirstName, LastName, Email, Phone, MobilePhone, Account.Name, Owner.Name "
                    "FROM Contact "
                    "WHERE (Phone != null OR MobilePhone != null) "
                    "ORDER BY Id DESC "
                    f"LIMIT {limit}"
                )
                self.logger.debug(f"SOQL Query (Contacts): {contact_query}")
                encoded_contact_query = urllib.parse.quote(contact_query)
                url_contact_query = (
                    f"{self._instance_url}/services/data/{self._version_api}/query/?q={encoded_contact_query}"
                )

                try:
                    resp = await client.get(url_contact_query, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    contact_records = data.get("records", [])

                    for contact in contact_records:
                        # Add Phone if available
                        if contact.get("Phone"):
                            phone_numbers.append({
                                "phone_number": contact.get("Phone"),
                                "type": "Contact",
                                "person_id": contact.get("Id"),
                                "first_name": contact.get("FirstName"),
                                "last_name": contact.get("LastName"),
                                "email": contact.get("Email"),
                                "account_name": contact.get("Account", {}).get("Name") if contact.get("Account") else None,
                                "owner_name": contact.get("Owner", {}).get("Name") if contact.get("Owner") else None,
                                "phone_type": "Phone"
                            })

                        # Add MobilePhone if available and different from Phone
                        if contact.get("MobilePhone") and contact.get("MobilePhone") != contact.get("Phone"):
                            phone_numbers.append({
                                "phone_number": contact.get("MobilePhone"),
                                "type": "Contact",
                                "person_id": contact.get("Id"),
                                "first_name": contact.get("FirstName"),
                                "last_name": contact.get("LastName"),
                                "email": contact.get("Email"),
                                "account_name": contact.get("Account", {}).get("Name") if contact.get("Account") else None,
                                "owner_name": contact.get("Owner", {}).get("Name") if contact.get("Owner") else None,
                                "phone_type": "MobilePhone"
                            })

                except httpx.HTTPStatusError as http_err:
                    self.logger.info(f"HTTP error querying Contacts: {http_err} - Status: {http_err.response.status_code}")
                    try:
                        self.logger.info(json.dumps(http_err.response.json(), indent=2, ensure_ascii=False))
                    except json.JSONDecodeError:
                        self.logger.info(http_err.response.text)
                    raise http_err
                except Exception as e:
                    self.logger.info(f"Error querying Contacts: {e!s}")
                    raise e

                # If we haven't reached the limit yet, get phone numbers from Leads
                remaining_limit = limit - len(phone_numbers)
                if remaining_limit > 0:
                    lead_query = (
                        "SELECT Id, FirstName, LastName, Email, Phone, MobilePhone, Company, Owner.Name, Status "
                        "FROM Lead "
                        "WHERE (Phone != null OR MobilePhone != null) AND IsConverted = false "
                        "ORDER BY Id DESC "
                        f"LIMIT {remaining_limit}"
                    )
                    self.logger.debug(f"SOQL Query (Leads): {lead_query}")
                    encoded_lead_query = urllib.parse.quote(lead_query)
                    url_lead_query = f"{self._instance_url}/services/data/{self._version_api}/query/?q={encoded_lead_query}"

                    try:
                        resp = await client.get(url_lead_query, headers=headers)
                        resp.raise_for_status()
                        data = resp.json()
                        lead_records = data.get("records", [])

                        for lead in lead_records:
                            # Add Phone if available
                            if lead.get("Phone"):
                                phone_numbers.append({
                                    "phone_number": lead.get("Phone"),
                                    "type": "Lead",
                                    "person_id": lead.get("Id"),
                                    "first_name": lead.get("FirstName"),
                                    "last_name": lead.get("LastName"),
                                    "email": lead.get("Email"),
                                    "company": lead.get("Company"),
                                    "owner_name": lead.get("Owner", {}).get("Name") if lead.get("Owner") else None,
                                    "status": lead.get("Status"),
                                    "phone_type": "Phone"
                                })

                            # Add MobilePhone if available and different from Phone
                            if lead.get("MobilePhone") and lead.get("MobilePhone") != lead.get("Phone"):
                                phone_numbers.append({
                                    "phone_number": lead.get("MobilePhone"),
                                    "type": "Lead",
                                    "person_id": lead.get("Id"),
                                    "first_name": lead.get("FirstName"),
                                    "last_name": lead.get("LastName"),
                                    "email": lead.get("Email"),
                                    "company": lead.get("Company"),
                                    "owner_name": lead.get("Owner", {}).get("Name") if lead.get("Owner") else None,
                                    "status": lead.get("Status"),
                                    "phone_type": "MobilePhone"
                                })

                    except httpx.HTTPStatusError as http_err:
                        self.logger.info(f"HTTP error querying Leads: {http_err} - Status: {http_err.response.status_code}")
                        try:
                            self.logger.info(json.dumps(http_err.response.json(), indent=2, ensure_ascii=False))
                        except json.JSONDecodeError:
                            self.logger.info(http_err.response.text)
                        raise http_err
                    except Exception as e:
                        self.logger.info(f"Error querying Leads: {e!s}")
                        raise e

                # Limit the results to the requested number
                phone_numbers = phone_numbers[:limit]
                self.logger.info(f"Retrieved {len(phone_numbers)} phone numbers from Salesforce")
                return phone_numbers

        try:
            return await self._with_auth_retry(_execute_phone_numbers_search)
        except (httpx.RequestError, Exception) as e:
            self.logger.info(f"Error retrieving phone numbers: {e!s}")
            return None

    @measure_latency(OperationType.SALESFORCE, provider="salesforce")
    async def create_contact_async(
        self,
        first_name: str,
        last_name: str,
        email: str | None = None,
        phone: str | None = None,
        mobile_phone: str | None = None,
        account_id: str | None = None,
        owner_id: str | None = None,
        title: str | None = None,
        department: str | None = None,
        description: str | None = None,
        **additional_fields
    ) -> str | None:
        """
        Create a new Contact in Salesforce.

        Args:
            first_name: Contact's first name (required)
            last_name: Contact's last name (required)
            email: Contact's email address
            phone: Contact's phone number
            mobile_phone: Contact's mobile phone number
            account_id: ID of the Account to associate with the contact
            owner_id: ID of the User who will own this contact
            title: Contact's job title
            department: Contact's department
            description: Additional description or notes
            **additional_fields: Any additional custom fields to set

        Returns:
            The ID of the created Contact if successful, None otherwise
        """
        await self._ensure_authenticated_async()

        if not first_name or not last_name:
            self.logger.error("Error: first_name and last_name are required to create a contact")
            return None

        self.logger.info(f"Creating new Contact: {first_name} {last_name}")

        async def _execute_contact_creation():
            headers = {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}

            # Prepare contact payload with required fields
            contact_payload = {
                "FirstName": first_name,
                "LastName": last_name
            }

            # Add optional fields if provided
            if email:
                contact_payload["Email"] = email
            if phone:
                contact_payload["Phone"] = phone
            if mobile_phone:
                contact_payload["MobilePhone"] = mobile_phone
            if account_id:
                contact_payload["AccountId"] = account_id
            if owner_id:
                contact_payload["OwnerId"] = owner_id
            if title:
                contact_payload["Title"] = title
            if department:
                contact_payload["Department"] = department
            if description:
                contact_payload["Description"] = description

            # Add any additional custom fields
            for field_name, field_value in additional_fields.items():
                if field_value is not None:
                    contact_payload[field_name] = field_value

            url_create_contact = f"{self._instance_url}/services/data/{self._version_api}/sobjects/Contact/"

            async with httpx.AsyncClient() as client:
                resp = await client.post(url_create_contact, headers=headers, json=contact_payload)
                resp.raise_for_status()

                contact_data = resp.json()
                contact_id = contact_data.get("id")

                if contact_id:
                    self.logger.info("Contact created successfully!")
                    self.logger.info(f"Contact ID: {contact_id}")
                    self.logger.info(f"View URL: {self._instance_url}/lightning/r/Contact/{contact_id}/view")
                    return contact_id
                else:
                    self.logger.error("Contact creation failed - no ID returned")
                    return None

        try:
            return await self._with_auth_retry(_execute_contact_creation)
        except httpx.HTTPStatusError as http_err:
            self.logger.error(f"Error creating Contact: {http_err.response.status_code}")
            try:
                self.logger.error(json.dumps(http_err.response.json(), indent=2, ensure_ascii=False))
            except Exception:
                self.logger.error(http_err.response.text)
            return None
        except Exception as e:
            self.logger.error(f"Error creating Contact: {e!s}")
            return None

    @measure_latency(OperationType.SALESFORCE, provider="salesforce")
    async def create_opportunity_async(
        self,
        name: str,
        stage_name: str,
        close_date: str,
        account_id: str | None = None,
        owner_id: str | None = None,
        contact_id: str | None = None,
        contact_role: str | None = "Decision Maker",
        converted_from_lead_id: str | None = None,
        amount: float | None = None,
        probability: int | None = None,
        description: str | None = None,
        lead_source: str | None = None,
        type_: str | None = None,
        next_step: str | None = None,
        **additional_fields
    ) -> str | None:
        """
        Create a new Opportunity in Salesforce with prospect linking support.

        Args:
            name: Opportunity name (required)
            stage_name: Sales stage name (required, e.g., "Prospecting", "Qualification", "Closed Won")
            close_date: Expected close date in YYYY-MM-DD format (required)
            account_id: ID of the Account associated with the opportunity
            owner_id: ID of the User who will own this opportunity
            contact_id: ID of the Contact to link directly to this opportunity (creates OpportunityContactRole)
            contact_role: Role of the contact in the opportunity (default: "Decision Maker")
            converted_from_lead_id: ID of the Lead this opportunity was converted from (for tracking)
            amount: Opportunity amount/value
            probability: Probability percentage (0-100)
            description: Opportunity description
            lead_source: Lead source (e.g., "Web", "Phone Inquiry", "Partner Referral")
            type_: Opportunity type (e.g., "Existing Customer - Upgrade", "New Customer")
            next_step: Next step in the sales process
            **additional_fields: Any additional custom fields to set

        Prospect Linking Options:
            1. Via Account: Pass account_id to link indirectly through Account relationship
            2. Via Contact: Pass contact_id to create direct Contact-Opportunity relationship
            3. Via Lead: Pass converted_from_lead_id to track lead conversion
            4. Combined: Use multiple linking methods for comprehensive tracking

        Examples:
            # Link via Account only
            opp_id = await client.create_opportunity_async(
                name="New Deal", stage_name="Prospecting", close_date="2025-12-31",
                account_id="001XXXXXXXXX"
            )

            # Link directly to Contact
            opp_id = await client.create_opportunity_async(
                name="New Deal", stage_name="Prospecting", close_date="2025-12-31",
                contact_id="003XXXXXXXXX", contact_role="Decision Maker"
            )

            # Track lead conversion
            opp_id = await client.create_opportunity_async(
                name="Converted Lead Deal", stage_name="Qualification", close_date="2025-12-31",
                account_id="001XXXXXXXXX", contact_id="003XXXXXXXXX",
                converted_from_lead_id="00QXXXXXXXXX"
            )

        Returns:
            The ID of the created Opportunity if successful, None otherwise
        """
        await self._ensure_authenticated_async()

        if not name or not stage_name or not close_date:
            self.logger.error("Error: name, stage_name, and close_date are required to create an opportunity")
            return None

        # Validate close_date format
        try:
            datetime.strptime(close_date, "%Y-%m-%d")
        except ValueError:
            self.logger.error("Error: close_date must be in YYYY-MM-DD format")
            return None

        self.logger.info(f"Creating new Opportunity: {name}")

        async def _execute_opportunity_creation():
            headers = {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}

            # Prepare opportunity payload with required fields
            opportunity_payload = {
                "Name": name,
                "StageName": stage_name,
                "CloseDate": close_date
            }

            # Add optional fields if provided
            if account_id:
                opportunity_payload["AccountId"] = account_id
            if owner_id:
                opportunity_payload["OwnerId"] = owner_id
            if amount is not None:
                opportunity_payload["Amount"] = amount
            if probability is not None:
                if 0 <= probability <= 100:
                    opportunity_payload["Probability"] = probability
                else:
                    self.logger.warning("Probability must be between 0 and 100, skipping this field")
            if description:
                opportunity_payload["Description"] = description
            if lead_source:
                opportunity_payload["LeadSource"] = lead_source
            if type_:
                opportunity_payload["Type"] = type_
            if next_step:
                opportunity_payload["NextStep"] = next_step

            # Add lead tracking if provided
            if converted_from_lead_id:
                # Note: This is for custom tracking, not a standard Salesforce field
                # Organizations may have custom fields like "Converted_From_Lead__c"
                opportunity_payload["Converted_From_Lead__c"] = converted_from_lead_id

            # Add any additional custom fields
            for field_name, field_value in additional_fields.items():
                if field_value is not None:
                    opportunity_payload[field_name] = field_value

            url_create_opportunity = f"{self._instance_url}/services/data/{self._version_api}/sobjects/Opportunity/"

            async with httpx.AsyncClient() as client:
                resp = await client.post(url_create_opportunity, headers=headers, json=opportunity_payload)
                resp.raise_for_status()

                opportunity_data = resp.json()
                opportunity_id = opportunity_data.get("id")

                if opportunity_id:
                    self.logger.info("Opportunity created successfully!")
                    self.logger.info(f"Opportunity ID: {opportunity_id}")
                    self.logger.info(f"View URL: {self._instance_url}/lightning/r/Opportunity/{opportunity_id}/view")

                    # Create OpportunityContactRole if contact_id is provided
                    if contact_id:
                        self.logger.info(f"Creating OpportunityContactRole for Contact: {contact_id}")
                        role_created = await self._create_opportunity_contact_role(
                            opportunity_id, contact_id, contact_role or "Decision Maker", client, headers
                        )
                        if not role_created:
                            self.logger.warning("Opportunity created but OpportunityContactRole creation failed")

                    return opportunity_id
                else:
                    self.logger.error("Opportunity creation failed - no ID returned")
                    return None

        try:
            return await self._with_auth_retry(_execute_opportunity_creation)
        except httpx.HTTPStatusError as http_err:
            self.logger.error(f"Error creating Opportunity: {http_err.response.status_code}")
            try:
                self.logger.error(json.dumps(http_err.response.json(), indent=2, ensure_ascii=False))
            except Exception:
                self.logger.error(http_err.response.text)
            return None
        except Exception as e:
            self.logger.error(f"Error creating Opportunity: {e!s}")
            return None
