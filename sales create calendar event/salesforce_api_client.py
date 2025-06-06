import jwt
import requests
import time
import json
import datetime
import httpx
import asyncio

class SalesforceApiClient:
    def __init__(self, client_id: str, username: str, private_key_file: str, is_sandbox: bool = True):
        self._client_id = client_id
        self._username = username
        self._private_key_file = private_key_file
        self._is_sandbox = is_sandbox
        
        # API settings
        salesforce_domain = 'salesforce.com'
        self.subdomain = 'test' if is_sandbox else 'login'
        self._auth_url = f'https://{self.subdomain}.{salesforce_domain}/services/oauth2/token'
        self._version_api = 'v60.0'
        
        # Auth results
        self._access_token = None
        self._instance_url = None
        self._async_client = httpx.AsyncClient() # Added for async operations
        self.authenticate()
    
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
            'aud': self._auth_url,
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
    
    def create_event(self, subject: str, start_datetime: str, duration_minutes: int = 60, description: str | None = None, 
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

    def _calculate_end_datetime(self, start_datetime: str, duration_minutes: int) -> str | None:
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

    async def _authenticate_async(self) -> bool:
        """Asynchronously authenticate with Salesforce using JWT and return success status"""
        print("Authenticating asynchronously via JWT...")
        try:
            with open(self._private_key_file, 'r') as f:
                private_key = f.read()
        except FileNotFoundError:
            print(f"Error: Private key file '{self._private_key_file}' not found")
            return False
        
        payload = {
            'iss': self._client_id,
            'sub': self._username,
            'aud': self._auth_url,
            'exp': int(time.time()) + 300
        }
        
        jwt_token = jwt.encode(payload, private_key, algorithm='RS256')
        
        params = {
            'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
            'assertion': jwt_token
        }
        
        try:
            async with self._async_client as client:
                resp = await client.post(self._auth_url, data=params)
            
            if resp.status_code != 200:
                print(f"Async authentication error: {resp.status_code}")
                try:
                    print(await resp.json())
                except:
                    print(await resp.text())
                return False
            
            data = resp.json()
            self._access_token = data['access_token']
            self._instance_url = data['instance_url']
            print("Async authentication successful!")
            return True
        except Exception as e:
            print(f"Async authentication error: {str(e)}")
            return False

    async def _ensure_authenticated_async(self) -> bool:
        """Ensure the client is authenticated, calling _authenticate_async if needed."""
        if not self._access_token or not self._instance_url:
            print("Not authenticated or token expired, attempting async authentication...")
            if not await self._authenticate_async():
                return False
        return True

    async def _create_sobject_async(self, sobject_name: str, payload: dict) -> str | None:
        """Generic helper to create an sObject asynchronously."""
        if not await self._ensure_authenticated_async():
            print(f"Error: Authentication failed, cannot create {sobject_name}.")
            return None

        headers = {
            'Authorization': f'Bearer {self._access_token}',
            'Content-Type': 'application/json'
        }
        url = f"{self._instance_url}/services/data/{self._version_api}/sobjects/{sobject_name}/"

        print(f"Creating {sobject_name} with payload: {json.dumps(payload)}")
        try:
            async with self._async_client as client:
                resp = await client.post(url, headers=headers, json=payload)
            
            if resp.status_code == 201: # Created
                created_id = resp.json().get('id')
                print(f"{sobject_name} created successfully! ID: {created_id}")
                return created_id
            else:
                print(f"Error creating {sobject_name}: {resp.status_code}")
                try:
                    error_details = await resp.json()
                    print(json.dumps(error_details, indent=2, ensure_ascii=False))
                except:
                    print(await resp.text())
                return None
        except Exception as e:
            print(f"Exception creating {sobject_name}: {str(e)}")
            return None

    async def _create_account_async(self, first_name: str, last_name: str, person_email: str, phone: str | None = None, record_type_id: str | None = None) -> str | None:
        """Creates a Person Account."""
        payload = {
            'FirstName': first_name,
            'LastName': last_name,
            'PersonEmail': person_email,
        }
        if phone: payload['Phone'] = phone
        # For Person Accounts, 'Name' is auto-populated. For business accounts, 'Name' would be explicit.
        # Assuming Person Account model here. If RecordTypeId for Person Account is known and required:
        if record_type_id: payload['RecordTypeId'] = record_type_id
        return await self._create_sobject_async('Account', payload)

    async def _create_contact_async(self, account_id: str, last_name: str, first_name: str, email: str, phone: str | None = None, birthdate: str | None = None) -> str | None:
        """Creates a Contact linked to an Account."""
        payload = {
            'AccountId': account_id,
            'LastName': last_name,
            'FirstName': first_name,
            'Email': email,
        }
        if phone: payload['Phone'] = phone
        if birthdate: payload['Birthdate'] = birthdate # Expected format YYYY-MM-DD
        return await self._create_sobject_async('Contact', payload)

    async def _create_lead_async(self, company: str, last_name: str, first_name: str, email: str, phone: str | None = None, 
                                 lead_source: str | None = None, country: str | None = None, thematique: str | None = None,
                                 ecole: str | None = None, formulaire: str | None = None, url: str | None = None,
                                 utm_campaign: str | None = None, utm_source: str | None = None, utm_medium: str | None = None, utm_content: str | None = None,
                                 request_host: str | None = None, request_path: str | None = None, # Changed from request_url to request_path
                                 consentement: str | None = None, training_course_id: str | None = None) -> str | None:
        """Creates a Lead."""
        payload = {
            'Company': company, # 'ecole' can be used here or a specific company name
            'LastName': last_name,
            'FirstName': first_name,
            'Email': email,
        }
        if phone: payload['Phone'] = phone
        if lead_source: payload['LeadSource'] = lead_source # Standard field, map 'formulaire' here if appropriate
        if country: payload['Country'] = country
        
        # Custom fields - ensure API names are correct for your Salesforce org
        if thematique: payload['Thematique__c'] = thematique
        if ecole: payload['Ecole__c'] = ecole # Specific custom field for school if 'Company' is different
        if formulaire: payload['Formulaire__c'] = formulaire # Specific custom field for form name
        if url: payload['Origin_URL__c'] = url
        if utm_campaign: payload['UTM_Campaign__c'] = utm_campaign
        if utm_source: payload['UTM_Source__c'] = utm_source
        if utm_medium: payload['UTM_Medium__c'] = utm_medium
        if utm_content: payload['UTM_Content__c'] = utm_content
        if request_host: payload['Request_Host__c'] = request_host
        if request_path: payload['Request_Path__c'] = request_path
        if consentement: payload['Consentement__c'] = consentement
        if training_course_id: payload['Training_Course_ID__c'] = training_course_id
        
        return await self._create_sobject_async('Lead', payload)

    async def _create_opportunity_async(self, account_id: str, name: str, stage_name: str, close_date: str, 
                                      contact_id: str | None = None, amount: float | None = None, 
                                      thematique: str | None = None, ecole: str | None = None, 
                                      formulaire: str | None = None, training_course_id: str | None = None) -> str | None:
        """Creates an Opportunity."""
        payload = {
            'AccountId': account_id,
            'Name': name,
            'StageName': stage_name, # E.g., 'Prospecting', 'Closed Won'
            'CloseDate': close_date, # Expected format YYYY-MM-DD
        }
        if contact_id: payload['ContactId'] = contact_id # Primary contact for the opportunity
        if amount: payload['Amount'] = amount
        
        # Custom fields - ensure API names are correct
        if thematique: payload['Thematique__c'] = thematique
        if ecole: payload['Ecole__c'] = ecole
        if formulaire: payload['Formulaire__c'] = formulaire
        if training_course_id: payload['Training_Course_ID__c'] = training_course_id
        # Consider mapping training_course_id to CORE_Main_Product_Interest__c if Product2 setup allows

        return await self._create_sobject_async('Opportunity', payload)

    async def create_sales_journey_async(self,
                                         email: str, nom: str, prenom: str, tel: str,
                                         thematique: str, ecole: str, formulaire: str, pays: str,
                                         utm_source: str, utm_medium: str, consentement: str, training_course_id: str,
                                         opportunity_stage_name: str, opportunity_close_date: str, # YYYY-MM-DD
                                         url: str | None = None, birthdate: str | None = None, # YYYY-MM-DD
                                         utm_campaign: str | None = None, utm_content: str | None = None,
                                         request_host: str | None = None, request_url_path: str | None = None, # path part of the URL
                                         account_name_override: str | None = None, # Not used if Person Account is default
                                         lead_company_override: str | None = None,
                                         opportunity_name_override: str | None = None,
                                         opportunity_amount: float | None = None,
                                         account_record_type_id: str | None = None) -> dict:
        """ 
        Orchestrates the creation of Account (Person Account), Contact, Lead, and Opportunity.
        Returns a dictionary with the IDs of created records.
        Dates (opportunity_close_date, birthdate) should be in 'YYYY-MM-DD' format.
        """
        results = {
            'account_id': None,
            'contact_id': None,
            'lead_id': None,
            'opportunity_id': None
        }

        # 1. Create Account (Person Account)
        # For Person Accounts, LastName is required. FirstName is recommended.
        # The Account Name is typically auto-generated from FirstName and LastName for Person Accounts.
        account_id = await self._create_account_async(
            first_name=prenom, 
            last_name=nom, 
            person_email=email, 
            phone=tel,
            record_type_id=account_record_type_id
        )
        if not account_id:
            print("Failed to create Account. Aborting sales journey.")
            return results
        results['account_id'] = account_id

        # 2. Create Contact
        contact_id = await self._create_contact_async(
            account_id=account_id,
            last_name=nom,
            first_name=prenom,
            email=email,
            phone=tel,
            birthdate=birthdate
        )
        if not contact_id:
            print("Failed to create Contact.") # Continue with Lead and Opp if Contact fails
        results['contact_id'] = contact_id

        # 3. Create Lead
        lead_company = lead_company_override if lead_company_override else ecole
        lead_id = await self._create_lead_async(
            company=lead_company,
            last_name=nom,
            first_name=prenom,
            email=email,
            phone=tel,
            lead_source=formulaire, # Or map to a specific LeadSource picklist value
            country=pays,
            thematique=thematique,
            ecole=ecole,
            formulaire=formulaire,
            url=url,
            utm_campaign=utm_campaign,
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_content=utm_content,
            request_host=request_host,
            request_path=request_url_path,
            consentement=consentement,
            training_course_id=training_course_id
        )
        results['lead_id'] = lead_id # Store lead_id even if None

        # 4. Create Opportunity
        opp_name = opportunity_name_override if opportunity_name_override else f"{prenom} {nom} - {thematique}"
        opportunity_id = await self._create_opportunity_async(
            account_id=account_id,
            name=opp_name,
            stage_name=opportunity_stage_name,
            close_date=opportunity_close_date,
            contact_id=contact_id, # Link the contact created earlier if successful
            amount=opportunity_amount,
            thematique=thematique,
            ecole=ecole,
            formulaire=formulaire,
            training_course_id=training_course_id
        )
        results['opportunity_id'] = opportunity_id # Store opp_id even if None
        
        print(f"Sales journey creation process finished. Results: {results}")
        return results
            
    def get_events(self, start_datetime: str, end_datetime: str, owner_id: str | None = None) -> list | None:
        """Get events from Salesforce calendar between specified start and end datetimes
        
        Args:
            start_datetime: Start date and time in ISO format (e.g., '2025-05-20T14:00:00Z')
            end_datetime: End date and time in ISO format (e.g., '2025-05-20T15:00:00Z')
            owner_id: Optional Salesforce ID to filter events by owner
            
        Returns:
            List of events if successful, None otherwise
        """
        if not self._access_token or not self._instance_url:
            print("Error: Not authenticated. Call authenticate() first.")
            return None
            
        print("Retrieving events...")
        
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
        encoded_query = requests.utils.quote(query)
        print(f"SOQL Query: {query}")
        
        # Create query URL
        url_query = f"{self._instance_url}/services/data/{self._version_api}/query/?q={encoded_query}"
        
        # Send request
        try:
            resp = requests.get(url_query, headers=headers)
            
            if resp.status_code == 200:
                data = resp.json()
                events = data.get('records', [])
                total_size = data.get('totalSize', 0)
                print(f"Retrieved {total_size} events")
                
                # Handle pagination if needed
                next_records_url = data.get('nextRecordsUrl')
                while next_records_url:
                    next_url = f"{self._instance_url}{next_records_url}"
                    resp = requests.get(next_url, headers=headers)
                    if resp.status_code == 200:
                        next_data = resp.json()
                        events.extend(next_data.get('records', []))
                        next_records_url = next_data.get('nextRecordsUrl')
                    else:
                        print(f"Error retrieving additional events: {resp.status_code}")
                        break
                return events
            else:
                print(f"Error retrieving events: {resp.status_code}")
                try:
                    print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
                except:
                    print(resp.text)
                return None
        except Exception as e:
            print(f"Error retrieving events: {str(e)}")
            return None

    def get_person_by_phone(self, phone_number: str) -> dict | None:
        """
        Retrieve a Contact or Lead from Salesforce by phone number.
        Searches Contacts first, then non-converted Leads if no Contact is found.

        Args:
            phone_number: The phone number to search for.

        Returns:
            A dictionary containing the person's type ('Contact' or 'Lead') and data,
            or None if no matching record is found.
        """
        if not self._access_token or not self._instance_url:
            print("Error: Not authenticated. Call authenticate() first.")
            return None

        headers = {
            'Authorization': f'Bearer {self._access_token}',
            'Content-Type': 'application/json'
        }

        # --- Try to find a Contact ---
        contact_query = (
            "SELECT Id, FirstName, LastName, Email, Phone, MobilePhone, Account.Id, Account.Name, Owner.Id, Owner.Name "
            "FROM Contact "
            f"WHERE Phone = '{phone_number}' OR MobilePhone = '{phone_number}' "
            "LIMIT 1"
        )
        print(f"SOQL Query (Contact): {contact_query}")
        encoded_contact_query = requests.utils.quote(contact_query)
        url_contact_query = f"{self._instance_url}/services/data/{self._version_api}/query/?q={encoded_contact_query}"

        try:
            resp = requests.get(url_contact_query, headers=headers)
            resp.raise_for_status() 
            data = resp.json()
            records = data.get('records', [])
            if records:
                contact_data = records[0]
                print(f"Found Contact: {contact_data.get('Id')} - {contact_data.get('FirstName')} {contact_data.get('LastName')}")
                return {'type': 'Contact', 'data': contact_data}
        except requests.exceptions.HTTPError as http_err:
            print(f"HTTP error querying Contact: {http_err} - {resp.status_code}")
            try:
                print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
            except json.JSONDecodeError:
                print(resp.text)
        except Exception as e:
            print(f"Exception querying Contact: {str(e)}")

        # --- If no Contact found, try to find a Lead ---
        lead_query = (
            "SELECT Id, FirstName, LastName, Email, Phone, MobilePhone, Company, Owner.Id, Owner.Name, Status, IsConverted "
            "FROM Lead "
            f"WHERE (Phone = '{phone_number}' OR MobilePhone = '{phone_number}') AND IsConverted = false "
            "LIMIT 1"
        )
        print(f"SOQL Query (Lead): {lead_query}")
        encoded_lead_query = requests.utils.quote(lead_query)
        url_lead_query = f"{self._instance_url}/services/data/{self._version_api}/query/?q={encoded_lead_query}"

        try:
            resp = requests.get(url_lead_query, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            records = data.get('records', [])
            if records:
                lead_data = records[0]
                print(f"Found Lead: {lead_data.get('Id')} - {lead_data.get('FirstName')} {lead_data.get('LastName')}")
                return {'type': 'Lead', 'data': lead_data}
        except requests.exceptions.HTTPError as http_err:
            print(f"HTTP error querying Lead: {http_err} - {resp.status_code}")
            try:
                print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
            except json.JSONDecodeError:
                print(resp.text)
        except Exception as e:
            print(f"Exception querying Lead: {str(e)}")
            
        print(f"No Contact or non-converted Lead found for phone number: {phone_number}")
        return None

    
    def discover_database(self, sobjects_to_describe: list[str] | None = None, include_fields: bool = True) -> dict | None:
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
        if not self._access_token or not self._instance_url:
            print("Error: Not authenticated. Call authenticate() first.")
            return None

        headers = {'Authorization': f'Bearer {self._access_token}'}
        schema = {}

        # 1. Get list of all SObjects metadata for URLs
        all_sobjects_url = f"{self._instance_url}/services/data/{self._version_api}/sobjects/"
        try:
            print("Fetching list of all SObjects...")
            resp = requests.get(all_sobjects_url, headers=headers)
            resp.raise_for_status()
            all_sobjects_data = resp.json()
        except requests.exceptions.HTTPError as http_err_main:
            print(f"HTTP error getting SObject list: {http_err_main} - Status: {resp.status_code if 'resp' in locals() else 'N/A'}")
            try: print(json.dumps(resp.json(), indent=2))
            except: print(resp.text if 'resp' in locals() else "No response text.")
            return None
        except Exception as e_main:
            print(f"Error fetching SObject list: {str(e_main)}")
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
            print(f"Will describe {len(target_sobjects_info)} specified SObjects: {', '.join(s_name for s_name in sobjects_to_describe)}")
        else:
            target_sobjects_info = [{'name': s_info['name'], 'describe_url_path': s_info['urls']['describe']}
                                   for s_info in all_sobjects_metadata_list
                                   if 'name' in s_info and 'urls' in s_info and 'describe' in s_info['urls']]
            print(f"Found {len(target_sobjects_info)} SObjects. Describing all can be very slow and consume many API calls.")

        total_objects_to_describe = len(target_sobjects_info)
        for i, sobject_item in enumerate(target_sobjects_info):
            s_name = sobject_item['name']
            describe_url = f"{self._instance_url}{sobject_item['describe_url_path']}"
            
            print(f"Describing SObject {i+1}/{total_objects_to_describe}: {s_name}...")
            try:
                desc_resp = requests.get(describe_url, headers=headers)
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
                    time.sleep(0.2) # 200ms delay

            except requests.exceptions.HTTPError as http_err_desc:
                error_detail = "Unknown error"
                try: error_detail = json.dumps(desc_resp.json(), indent=2)
                except: error_detail = desc_resp.text if 'desc_resp' in locals() and hasattr(desc_resp, 'text') else "No response text."
                print(f"HTTP error describing SObject {s_name}: {http_err_desc} - Status: {desc_resp.status_code if 'desc_resp' in locals() else 'N/A'}. Details: {error_detail[:500]}")
                schema[s_name] = {'error': f'Failed to describe: {str(http_err_desc)}'}
            except Exception as e_desc:
                print(f"Error describing SObject {s_name}: {str(e_desc)}")
                schema[s_name] = {'error': f'Failed to describe: {str(e_desc)}'}
        
        return schema
    def _query_salesforce(self, soql_query: str) -> dict | None:
        """Helper method to execute a SOQL query and return the full JSON response.

        Args:
            soql_query: The SOQL query string.

        Returns:
            The full JSON response dictionary from Salesforce (includes 'records',
            'totalSize', 'done', 'nextRecordsUrl'), or None if an error occurs.
        """
        if not self._access_token or not self._instance_url:
            # This should ideally be checked before calling _query_salesforce by public methods
            print("Error: Not authenticated. Call authenticate() first.") 
            return None

        headers = {'Authorization': f'Bearer {self._access_token}'}
        encoded_query = requests.utils.quote(soql_query)
        url_query = f"{self._instance_url}/services/data/{self._version_api}/query/?q={encoded_query}"
        
        # print(f"Executing SOQL: {soql_query}") # Verbose, enable for deep debugging
        try:
            resp = requests.get(url_query, headers=headers)
            resp.raise_for_status() # Will raise HTTPError for 4xx/5xx status codes
            return resp.json()
        except requests.exceptions.HTTPError as http_err:
            error_message = f"SOQL Query HTTP error: {http_err} - Status: {resp.status_code if 'resp' in locals() else 'N/A'}. Query: {soql_query}"
            print(error_message)
            try: 
                error_details = resp.json()
                print(json.dumps(error_details, indent=2))
            except json.JSONDecodeError:
                print(f"Response text: {resp.text if 'resp' in locals() else 'No response text available.'}")
            return None
        except Exception as e:
            print(f"SOQL Query general error: {str(e)}. Query: {soql_query}")
            return None

    def get_leads_by_details(self, email: str | None = None, first_name: str | None = None, last_name: str | None = None, company_name: str | None = None) -> list[dict] | None:
        """
        Retrieve active (non-converted) Leads based on email, name, or company.
        Args:
            email: Email address to search for.
            first_name: First name to search for (requires last_name for effective name search).
            last_name: Last name to search for (requires first_name for effective name search).
            company_name: Company name to search for.
        Returns:
            A list of matching Lead dictionaries, or None if a query error occurs.
            Returns an empty list if no matches are found but the query was successful.
        """
        if not self._access_token or not self._instance_url: # Initial auth check for the public method
            print("Error: Not authenticated. Call authenticate() first.") 
            return None

        conditions = ["IsConverted = false"]
        if email:
            conditions.append(f"Email = '{email}'")
        if first_name and last_name:
            conditions.append(f"(FirstName = '{first_name}' AND LastName = '{last_name}')")
        elif first_name or last_name:
            print("Warning: For name-based Lead search, providing both first_name and last_name is recommended for accuracy.")
            if first_name: conditions.append(f"FirstName = '{first_name}'")
            if last_name: conditions.append(f"LastName = '{last_name}'")
        if company_name:
            conditions.append(f"Company = '{company_name}'")

        # if len(conditions) == 1: # Only IsConverted = false, no other criteria
        #     print("Error: At least one search criterion (email, full name, or company) must be provided for get_leads_by_details.")
        #     return None # Or an empty list if that's preferred for bad input

        query_filter = " AND ".join(f"({c})" for c in conditions)
        
        soql_query = (
            "SELECT Id, FirstName, LastName, Email, Company, Status, Owner.Name, CreatedDate "
            "FROM Lead "
            f"WHERE {query_filter} "
            "ORDER BY CreatedDate DESC LIMIT 200" # Added LIMIT for safety
        )
        
        response_data = self._query_salesforce(soql_query)
        if response_data and response_data.get('records') is not None:
            return response_data['records']
        elif response_data is None: # Error occurred in _query_salesforce
            return None
        else: # Query successful, but no records found (e.g. response_data['records'] is empty list)
            return []

    def get_opportunities_for_lead(self, lead_id: str | None = None) -> list[dict] | None:
        """
        Retrieve Opportunities related to a specific Lead, primarily if converted.
        Args:
            lead_id: The ID of the Salesforce Lead.
        Returns:
            A list of Opportunity dictionaries. Prioritizes ConvertedOpportunityId,
            then searches by ConvertedAccountId. Returns None on error, empty list if no related Opps found.
        """
        if not self._access_token or not self._instance_url:
            print("Error: Not authenticated. Call authenticate() first.") 
            return None

        conditions = ""
        if lead_id:
            conditions = f"WHERE Id = '{lead_id}'"

        # Step 1: Get Lead conversion details
        lead_info_soql = f"SELECT Id, IsConverted, ConvertedOpportunityId, ConvertedAccountId FROM Lead {conditions} ORDER BY CreatedDate DESC LIMIT 200"
        lead_response = self._query_salesforce(lead_info_soql)

        if not lead_response or lead_response.get('records') is None:
            # _query_salesforce would have printed an error if lead_response is None
            # If records is None (but lead_response isn't), or empty, Lead not found or query issue.
            if lead_response and lead_response.get('totalSize', 0) == 0:
                 print(f"Lead with ID '{lead_id}' not found.")
                 return []
            return None # Error occurred during query
        
        lead_data = lead_response['records'][0]
        is_converted = lead_data.get('IsConverted')
        converted_opp_id = lead_data.get('ConvertedOpportunityId')
        converted_acc_id = lead_data.get('ConvertedAccountId')

        opportunity_soql = ""
        common_opp_fields = "SELECT Id, Name, StageName, Amount, CloseDate, AccountId, Account.Name, Owner.Name, CreatedDate FROM Opportunity"

        if is_converted and converted_opp_id:
            print(f"Lead '{lead_id}' was converted to Opportunity ID: '{converted_opp_id}'. Fetching this Opportunity.")
            opportunity_soql = f"{common_opp_fields} WHERE Id = '{converted_opp_id}' LIMIT 1"
        elif is_converted and converted_acc_id:
            print(f"Lead '{lead_id}' was converted to Account ID: '{converted_acc_id}'. Searching Opportunities for this Account.")
            opportunity_soql = f"{common_opp_fields} WHERE AccountId = '{converted_acc_id}' ORDER BY CreatedDate DESC LIMIT 200"
        else:
            print(f"Lead '{lead_id}' is not converted, or no ConvertedOpportunityId/ConvertedAccountId found. No direct Opportunities from conversion.")
            return []

        opp_response = self._query_salesforce(opportunity_soql)
        if opp_response and opp_response.get('records') is not None:
            return opp_response['records']
        elif opp_response is None: # Error in _query_salesforce
            return None 
        else: # Query successful, but no records (e.g. opp_response['records'] is empty list)
            return []
