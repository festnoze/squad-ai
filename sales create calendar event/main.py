import jwt
import requests
import time
import json
import datetime
from typing import Optional


class SalesforceEventManager:
    def __init__(self, client_id: str, username: str, private_key_file: str, is_sandbox: bool = True):
        self._client_id = client_id
        self._username = username
        self._private_key_file = private_key_file
        self._is_sandbox = is_sandbox
        
        # API settings
        self._auth_domain = 'test.salesforce.com' if is_sandbox else 'login.salesforce.com'
        self._auth_url = f'https://{self._auth_domain}/services/oauth2/token'
        self._version_api = 'v60.0'
        
        # Auth results
        self._access_token = None
        self._instance_url = None
    

    
    def authenticate(self) -> bool:
        """Authenticate with Salesforce using JWT and return success status"""
        print("Authenticating via JWT...")
        
        # Read private key
        try:
            with open(self._private_key_file, 'r') as f:
                private_key = f.read()
        except FileNotFoundError:
            print(f"Error: Private key file '{self._private_key_file}' not found")
            return False
        
        # Create JWT payload
        payload = {
            'iss': self._client_id,
            'sub': self._username,
            'aud': f'https://{self._auth_domain}',
            'exp': int(time.time()) + 300
        }
        
        # Encode JWT
        jwt_token = jwt.encode(payload, private_key, algorithm='RS256')
        
        # Prepare authentication request
        params = {
            'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
            'assertion': jwt_token
        }
        
        # Send authentication request
        try:
            resp = requests.post(self._auth_url, data=params)
            if resp.status_code != 200:
                print(f"Authentication error: {resp.status_code}")
                try:
                    print(resp.json())
                except:
                    print(resp.text)
                return False
            
            # Store authentication results
            data = resp.json()
            self._access_token = data['access_token']
            self._instance_url = data['instance_url']
            print("Authentication successful!")
            return True
        except Exception as e:
            print(f"Authentication error: {str(e)}")
            return False
    
    def create_event(self, subject: str, start_datetime: str, duration_minutes: int = 60, description: Optional[str] = None, 
                   location: Optional[str] = None, owner_id: Optional[str] = None, 
                   what_id: Optional[str] = None, who_id: Optional[str] = None) -> Optional[str]:
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
        if not self._access_token or not self._instance_url:
            print("Error: Not authenticated. Call authenticate() first.")
            return None
        
        if not subject or not start_datetime:
            print("Error: Required event fields (subject, start_datetime) are missing")
            return None
            
        end_datetime = self._calculate_end_datetime(start_datetime, duration_minutes)
        if not end_datetime:
            print("Error: Invalid start_datetime or duration_minutes")
            return None
        
        print("Creating the Event...")
        
        # Prepare headers
        headers = {
            'Authorization': f'Bearer {self._access_token}',
            'Content-Type': 'application/json'
        }
        
        # Prepare event payload
        payload_event = {
            'Subject': subject,
            'StartDateTime': start_datetime,
            'EndDateTime': end_datetime
        }
        
        # Add optional fields if they exist
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
        
        # Create event URL
        url_creation_event = f"{self._instance_url}/services/data/{self._version_api}/sobjects/Event/"
        
        # Send request
        try:
            resp_event = requests.post(url_creation_event, headers=headers, data=json.dumps(payload_event))
            
            if resp_event.status_code == 201:
                event_id = resp_event.json().get('id')
                print("Event created successfully!")
                print(f"ID: {event_id}")
                print(f"{self._instance_url}/lightning/r/Event/{event_id}/view")
                return event_id
            else:
                print(f"Error while creating the Event: {resp_event.status_code}")
                try:
                    print(json.dumps(resp_event.json(), indent=2, ensure_ascii=False))
                except:
                    print(resp_event.text)
                return None
        except Exception as e:
            print(f"Error creating event: {str(e)}")
            return None

    def _calculate_end_datetime(self, start_datetime: str, duration_minutes: int) -> Optional[str]:
        try:
            # Parse the ISO format datetime string
            start_dt = datetime.datetime.fromisoformat(start_datetime.replace('Z', '+00:00'))
            # Add the duration in minutes
            end_dt = start_dt + datetime.timedelta(minutes=duration_minutes)
            # Convert back to ISO format string
            end_datetime = end_dt.isoformat().replace('+00:00', 'Z')
            return end_datetime
        except ValueError as e:
            print(f"Error parsing start_datetime: {e}")
            print("Make sure start_datetime is in ISO format (e.g., '2025-05-20T14:00:00Z')")
            return None

# Example usage
if __name__ == "__main__":
    # Initialize the manager with credentials
    event_manager = SalesforceEventManager(
        client_id='3MVG9IKwJOi7clC2.8QIzh9BkM6NhU53bup6EUfFQiXJ01nh.l2YJKF5vbNWqPkFEdjgzAXIqK3U1p2WCBUD3',
        username='etienne.millerioux@studi.fr',#'axel.montzamir@studi.fr',
        private_key_file='server.key',
        is_sandbox=True
    )
    
    # Authenticate and create the event
    if event_manager.authenticate():
        event_id = event_manager.create_event(
            subject='Réunion de démonstration prise rendez-vous avec Twilio',
            description='Présentation des nouvelles fonctionnalités à un CdP.',
            start_datetime='2025-05-20T14:00:00Z',
            duration_minutes=30,
            location='Salle de conférence Alpha',
            owner_id='005Aa00000K990ZIAR',
            what_id='006Aa00000Ii3XoIAJ'  # Related to (Account, Opportunity, etc.)
            # who_id=''  # Associated with (Contact, Lead)
        )
        if event_id:
            print(f"Event created with ID: {event_id}")
