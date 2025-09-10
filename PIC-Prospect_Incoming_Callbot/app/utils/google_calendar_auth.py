"""
Google Calendar Authentication Helper

This module provides authentication utilities for Google Calendar API using service account credentials.
"""

import json
import logging
from pathlib import Path
from typing import Any

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from utils.envvar import EnvHelper


class GoogleCalendarAuth:
    """Helper class for Google Calendar API authentication using service account"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._service = None
        self._credentials = None
        
    def authenticate(self) -> bool:
        """
        Authenticate with Google Calendar API using service account credentials
        
        Returns:
            bool: True if authentication successful, False otherwise
        """
        try:
            credentials_path = EnvHelper.get_google_calendar_credentials_filepath()
            
            if not Path(credentials_path).exists():
                self.logger.error(f"Google Calendar credentials file not found: {credentials_path}")
                return False
                
            # Load service account credentials
            self._credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            
            # Build the Calendar service
            self._service = build('calendar', 'v3', credentials=self._credentials)
            
            # Test authentication by listing calendars
            calendar_list = self._service.calendarList().list().execute()
            self.logger.info(f"Successfully authenticated with Google Calendar API. Found {len(calendar_list.get('items', []))} calendars.")
            
            return True
            
        except FileNotFoundError:
            self.logger.error(f"Google Calendar credentials file not found: {credentials_path}")
            return False
        except json.JSONDecodeError:
            self.logger.error(f"Invalid JSON in Google Calendar credentials file: {credentials_path}")
            return False
        except GoogleAuthError as e:
            self.logger.error(f"Google Calendar authentication error: {e}")
            return False
        except HttpError as e:
            self.logger.error(f"Google Calendar API HTTP error during authentication: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during Google Calendar authentication: {e}")
            return False
    
    def get_service(self):
        """
        Get the authenticated Google Calendar service object
        
        Returns:
            googleapiclient.discovery.Resource: The Calendar service object
            
        Raises:
            RuntimeError: If not authenticated
        """
        if not self._service:
            raise RuntimeError("Not authenticated with Google Calendar API. Call authenticate() first.")
        return self._service
    
    def is_authenticated(self) -> bool:
        """
        Check if currently authenticated with Google Calendar API
        
        Returns:
            bool: True if authenticated, False otherwise
        """
        return self._service is not None
    
    def refresh_credentials(self) -> bool:
        """
        Refresh the authentication credentials
        
        Returns:
            bool: True if refresh successful, False otherwise
        """
        if not self._credentials:
            self.logger.warning("No credentials to refresh. Re-authenticating...")
            return self.authenticate()
            
        try:
            if self._credentials.expired:
                self._credentials.refresh(Request())
                self.logger.info("Google Calendar credentials refreshed successfully")
                return True
            else:
                self.logger.debug("Google Calendar credentials are still valid")
                return True
                
        except GoogleAuthError as e:
            self.logger.error(f"Failed to refresh Google Calendar credentials: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error refreshing Google Calendar credentials: {e}")
            return False
    
    def test_connection(self) -> bool:
        """
        Test the connection to Google Calendar API
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            if not self.is_authenticated():
                self.logger.error("Cannot test connection: not authenticated")
                return False
                
            # Try to get calendar info
            calendar_id = EnvHelper.get_google_calendar_id()
            calendar_info = self._service.calendars().get(calendarId=calendar_id).execute()
            
            self.logger.info(f"Connection test successful. Calendar: {calendar_info.get('summary', 'Unknown')}")
            return True
            
        except HttpError as e:
            self.logger.error(f"Google Calendar API connection test failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during connection test: {e}")
            return False