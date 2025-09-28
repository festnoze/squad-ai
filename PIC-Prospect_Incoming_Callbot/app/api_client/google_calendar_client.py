"""
Google Calendar Client Implementation

This module provides a Google Calendar implementation of the CalendarClientInterface.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

import pytz
from googleapiclient.errors import HttpError

from .calendar_client_interface import CalendarClientInterface
from utils.envvar import EnvHelper
from utils.google_calendar_auth import GoogleCalendarAuth
from utils.latency_decorator import measure_latency
from utils.latency_metric import OperationType


class GoogleCalendarClient(CalendarClientInterface):
    """Google Calendar implementation of CalendarClientInterface"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.auth_helper = GoogleCalendarAuth()
        self.calendar_id = EnvHelper.get_google_calendar_id()
        self.timezone = EnvHelper.get_google_calendar_timezone()
        
        # Authenticate eagerly
        self.authenticate()
    
    def authenticate(self) -> bool:
        """Authenticate with Google Calendar API and return success status"""
        success = self.auth_helper.authenticate()
        if success:
            self.logger.info("Google Calendar authentication successful")
        else:
            self.logger.error("Google Calendar authentication failed")
        return success
    
    async def _ensure_authenticated_async(self):
        """Ensure the client is authenticated before making API calls"""
        if not self.auth_helper.is_authenticated():
            if not self.authenticate():
                raise Exception("Google Calendar authentication failed. Cannot proceed with API call.")
        
        # Refresh credentials if needed
        if not self.auth_helper.refresh_credentials():
            raise Exception("Failed to refresh Google Calendar credentials.")
    
    @measure_latency(OperationType.CALENDAR, provider="google")
    async def schedule_new_appointment_async(
        self,
        subject: str,
        start_datetime: str,
        duration_minutes: int = 60,
        description: str | None = None,
        location: str | None = None,
        owner_id: str | None = None,
        what_id: str | None = None,
        who_id: str | None = None,
        max_retries: int = 2,
        retry_delay: float = 1.0,
    ) -> str | None:
        """Create an event in Google Calendar and return the event ID if successful"""
        await self._ensure_authenticated_async()
        
        if not subject or not start_datetime:
            self.logger.error("Error: Required event fields (subject, start_datetime) are missing")
            return None
        
        try:
            # Parse and convert datetime
            start_dt = self._parse_datetime(start_datetime)
            if not start_dt:
                self.logger.error("Error: Invalid start_datetime format")
                return None
            
            end_dt = start_dt + timedelta(minutes=duration_minutes)
            
            # Check for conflicts first
            existing_events = await self.get_scheduled_appointments_async(
                start_datetime=start_dt.isoformat(),
                end_datetime=end_dt.isoformat()
            )
            
            if existing_events:
                self.logger.error(f"Error: Calendar conflict detected. Found {len(existing_events)} existing events in the time slot.")
                return None
            
            # Create event object
            event = {
                'summary': subject,
                'start': {
                    'dateTime': start_dt.isoformat(),
                    'timeZone': self.timezone,
                },
                'end': {
                    'dateTime': end_dt.isoformat(),
                    'timeZone': self.timezone,
                },
            }
            
            if description:
                event['description'] = description
            if location:
                event['location'] = location
            
            # Create the event
            service = self.auth_helper.get_service()
            created_event = service.events().insert(
                calendarId=self.calendar_id,
                body=event
            ).execute()
            
            event_id = created_event.get('id')
            self.logger.info(f"Google Calendar event created successfully. Event ID: {event_id}")
            self.logger.info(f"Event URL: {created_event.get('htmlLink', 'N/A')}")
            
            return event_id
            
        except HttpError as e:
            self.logger.error(f"Google Calendar API error while creating event: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while creating Google Calendar event: {e}")
            return None
    
    @measure_latency(OperationType.CALENDAR, provider="google")
    async def get_scheduled_appointments_async(self, start_datetime: str, end_datetime: str, owner_id: str | None = None, user_id: str | None = None) -> list[dict]:
        """Get events from Google Calendar between specified start and end datetimes

        Note: For Google Calendar, user_id filtering is not applicable as it's a personal calendar.
        The parameter is included for interface compatibility.
        """
        await self._ensure_authenticated_async()
        
        try:
            # Parse datetimes
            time_min = self._parse_datetime(start_datetime)
            time_max = self._parse_datetime(end_datetime)
            
            if not time_min or not time_max:
                self.logger.error("Error: Invalid datetime format in get_scheduled_appointments_async")
                return []
            
            # Query Google Calendar API
            service = self.auth_helper.get_service()
            events_result = service.events().list(
                calendarId=self.calendar_id,
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            # Convert to expected format
            formatted_events = []
            for event in events:
                start = event.get('start', {})
                end = event.get('end', {})
                
                formatted_event = {
                    'Id': event.get('id'),
                    'Subject': event.get('summary', ''),
                    'Description': event.get('description', ''),
                    'StartDateTime': start.get('dateTime', start.get('date')),
                    'EndDateTime': end.get('dateTime', end.get('date')),
                    'Location': event.get('location', ''),
                    'OwnerId': owner_id,  # Google Calendar doesn't have the same owner concept
                    'WhatId': None,  # Not applicable to Google Calendar
                    'WhoId': None,   # Not applicable to Google Calendar
                }
                formatted_events.append(formatted_event)
            
            self.logger.info(f"Retrieved {len(formatted_events)} events from Google Calendar")
            return formatted_events
            
        except HttpError as e:
            self.logger.error(f"Google Calendar API error while retrieving events: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving Google Calendar events: {e}")
            return []
    
    @measure_latency(OperationType.CALENDAR, provider="google")
    async def verify_appointment_existance_async(
        self, 
        event_id: str | None = None, 
        expected_subject: str | None = None, 
        start_datetime: str = "", 
        duration_minutes: int = 30
    ) -> str | None:
        """Check if an appointment exists based on provided criteria"""
        await self._ensure_authenticated_async()
        
        try:
            if event_id:
                # Check specific event by ID
                service = self.auth_helper.get_service()
                try:
                    event = service.events().get(
                        calendarId=self.calendar_id,
                        eventId=event_id
                    ).execute()
                    
                    self.logger.info(f"Found Google Calendar event by ID: {event_id}")
                    return event_id
                except HttpError as e:
                    if e.resp.status == 404:
                        self.logger.info(f"Google Calendar event not found with ID: {event_id}")
                        return None
                    raise
            
            # Search by time window and/or subject
            if start_datetime:
                start_dt = self._parse_datetime(start_datetime)
                if not start_dt:
                    self.logger.error("Error: Invalid start_datetime format for verification")
                    return None
                
                end_dt = start_dt + timedelta(minutes=duration_minutes)
                
                # Search for events in time window
                events = await self.get_scheduled_appointments_async(
                    start_datetime=start_dt.isoformat(),
                    end_datetime=end_dt.isoformat()
                )
                
                for event in events:
                    if expected_subject:
                        if event.get('Subject') == expected_subject:
                            found_id = event.get('Id')
                            self.logger.info(f"Found Google Calendar event with subject '{expected_subject}': {found_id}")
                            return found_id
                    else:
                        # Return first event if no specific subject required
                        found_id = event.get('Id')
                        self.logger.info(f"Found Google Calendar event in time window: {found_id}")
                        return found_id
            
            self.logger.info("No matching Google Calendar event found")
            return None
            
        except Exception as e:
            self.logger.error(f"Error during Google Calendar appointment verification: {e}")
            return None
    
    @measure_latency(OperationType.CALENDAR, provider="google")
    async def delete_event_by_id_async(self, event_id: str) -> bool:
        """Delete an event from Google Calendar by its ID"""
        await self._ensure_authenticated_async()
        
        try:
            service = self.auth_helper.get_service()
            service.events().delete(
                calendarId=self.calendar_id,
                eventId=event_id
            ).execute()
            
            self.logger.info(f"Google Calendar event deleted successfully: {event_id}")
            return True
            
        except HttpError as e:
            if e.resp.status == 404:
                self.logger.warning(f"Google Calendar event not found for deletion: {event_id}")
                return False
            self.logger.error(f"Google Calendar API error while deleting event: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while deleting Google Calendar event: {e}")
            return False
    
    async def get_appointment_slots_async(
        self,
        start_datetime: str,
        end_datetime: str,
        work_type_id: str | None = None,
        service_territory_id: str | None = None,
    ) -> list[dict] | None:
        """
        Get available appointment slots for Google Calendar.
        Note: Google Calendar doesn't have built-in appointment slot functionality like Salesforce.
        This method returns time slots where no events are scheduled.
        """
        await self._ensure_authenticated_async()
        
        try:
            # Get existing appointments in the time range
            existing_events = await self.get_scheduled_appointments_async(start_datetime, end_datetime)
            
            # Parse time range
            start_dt = self._parse_datetime(start_datetime)
            end_dt = self._parse_datetime(end_datetime)
            
            if not start_dt or not end_dt:
                self.logger.error("Error: Invalid datetime format in get_appointment_slots_async")
                return None
            
            # Generate available slots (simplified approach - 30-minute slots during business hours)
            available_slots = []
            current_time = start_dt.replace(hour=9, minute=0, second=0, microsecond=0)  # Start at 9 AM
            end_time = min(end_dt, start_dt.replace(hour=17, minute=0, second=0, microsecond=0))  # End at 5 PM
            
            while current_time < end_time:
                slot_end = current_time + timedelta(minutes=30)
                
                # Check if this slot conflicts with existing events
                is_available = True
                for event in existing_events:
                    event_start = self._parse_datetime(event.get('StartDateTime', ''))
                    event_end = self._parse_datetime(event.get('EndDateTime', ''))
                    
                    if event_start and event_end:
                        if not (slot_end <= event_start or current_time >= event_end):
                            is_available = False
                            break
                
                if is_available:
                    available_slots.append({
                        'startTime': current_time.isoformat(),
                        'endTime': slot_end.isoformat(),
                        'id': f"slot_{current_time.strftime('%Y%m%d_%H%M')}",
                        'available': True
                    })
                
                current_time += timedelta(minutes=30)
            
            self.logger.info(f"Found {len(available_slots)} available appointment slots in Google Calendar")
            return available_slots
            
        except Exception as e:
            self.logger.error(f"Error retrieving Google Calendar appointment slots: {e}")
            return None
    
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
        Create an appointment using Google Calendar.
        Note: Google Calendar doesn't have Lightning Scheduler, so this delegates to regular appointment scheduling.
        """
        self.logger.info("Google Calendar doesn't support Lightning Scheduler. Using regular appointment scheduling.")
        
        return await self.schedule_new_appointment_async(
            subject=subject,
            start_datetime=start_datetime,
            duration_minutes=duration_minutes,
            description=description,
            location=None,  # Google Calendar uses location differently
            max_retries=max_retries,
            retry_delay=retry_delay
        )
    
    def _parse_datetime(self, datetime_str: str) -> datetime | None:
        """Parse datetime string to datetime object with timezone awareness"""
        if not datetime_str:
            return None
            
        try:
            # Handle various datetime formats
            if datetime_str.endswith('Z'):
                # UTC format
                dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                # Convert to configured timezone
                timezone = pytz.timezone(self.timezone)
                return dt.astimezone(timezone)
            elif '+' in datetime_str or datetime_str.endswith(tuple([f'{i:+03d}:00' for i in range(-12, 13)])):
                # Already has timezone
                dt = datetime.fromisoformat(datetime_str)
                timezone = pytz.timezone(self.timezone)
                return dt.astimezone(timezone)
            else:
                # Assume local timezone
                dt = datetime.fromisoformat(datetime_str)
                timezone = pytz.timezone(self.timezone)
                return timezone.localize(dt)
                
        except (ValueError, TypeError) as e:
            self.logger.error(f"Error parsing datetime '{datetime_str}': {e}")
            return None