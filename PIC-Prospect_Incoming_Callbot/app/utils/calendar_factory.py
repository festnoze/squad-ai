"""
Calendar Factory

This module provides a factory for creating calendar client instances based on configuration.
"""

import logging
from typing import Type

from api_client.calendar_client_interface import CalendarClientInterface
from api_client.google_calendar_client import GoogleCalendarClient
from api_client.salesforce_api_client import SalesforceApiClient
from utils.envvar import EnvHelper


class CalendarFactory:
    """Factory class for creating calendar client instances"""
    
    @staticmethod
    def create_calendar_client() -> CalendarClientInterface:
        """
        Create a calendar client instance based on the configured provider
        
        Returns:
            CalendarClientInterface: The appropriate calendar client implementation
            
        Raises:
            ValueError: If the configured provider is not supported
        """
        logger = logging.getLogger(__name__)
        provider = EnvHelper.get_calendar_provider().lower()
        
        if provider == "google":
            logger.info("Creating Google Calendar client")
            return GoogleCalendarClient()
        elif provider == "salesforce":
            logger.info("Creating Salesforce Calendar client")
            return SalesforceApiClient()  # Implements CalendarClientInterface
        else:
            raise ValueError(f"Unsupported calendar provider: {provider}. Supported providers: 'google', 'salesforce'")
    
    @staticmethod
    def get_supported_providers() -> list[str]:
        """
        Get a list of supported calendar providers
        
        Returns:
            list[str]: List of supported provider names
        """
        return ["google", "salesforce"]
    
    @staticmethod
    def get_calendar_client_class(provider: str) -> Type[CalendarClientInterface]:
        """
        Get the calendar client class for a specific provider
        
        Args:
            provider: The calendar provider name
            
        Returns:
            Type[CalendarClientInterface]: The calendar client class
            
        Raises:
            ValueError: If the provider is not supported
        """
        provider = provider.lower()
        
        if provider == "google":
            return GoogleCalendarClient
        elif provider == "salesforce":
            return SalesforceApiClient
        else:
            raise ValueError(f"Unsupported calendar provider: {provider}. Supported providers: {CalendarFactory.get_supported_providers()}")


# Example usage functions
async def example_schedule_appointment():
    """Example: Schedule an appointment using the configured calendar provider"""
    import asyncio
    from datetime import datetime, timedelta
    
    logger = logging.getLogger(__name__)
    
    try:
        # Create calendar client based on configuration
        calendar_client = CalendarFactory.create_calendar_client()
        
        # Schedule an appointment for tomorrow at 2 PM
        tomorrow = datetime.now() + timedelta(days=1)
        appointment_time = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)
        
        event_id = await calendar_client.schedule_new_appointment_async(
            subject="Test Appointment",
            start_datetime=appointment_time.isoformat() + "Z",
            duration_minutes=30,
            description="This is a test appointment created via Calendar Factory"
        )
        
        if event_id:
            logger.info(f"Successfully created appointment with ID: {event_id}")
            return event_id
        else:
            logger.error("Failed to create appointment")
            return None
            
    except Exception as e:
        logger.error(f"Error in example_schedule_appointment: {e}")
        return None


async def example_get_appointments():
    """Example: Get appointments for today using the configured calendar provider"""
    from datetime import datetime
    
    logger = logging.getLogger(__name__)
    
    try:
        # Create calendar client based on configuration
        calendar_client = CalendarFactory.create_calendar_client()
        
        # Get appointments for today
        today = datetime.now()
        start_of_day = today.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = today.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        appointments = await calendar_client.get_scheduled_appointments_async(
            start_datetime=start_of_day.isoformat() + "Z",
            end_datetime=end_of_day.isoformat() + "Z"
        )
        
        logger.info(f"Found {len(appointments)} appointments for today")
        for appointment in appointments:
            logger.info(f"  - {appointment.get('Subject', 'No Subject')} at {appointment.get('StartDateTime', 'Unknown time')}")
        
        return appointments
        
    except Exception as e:
        logger.error(f"Error in example_get_appointments: {e}")
        return []


def example_provider_comparison():
    """Example: Compare different calendar providers"""
    logger = logging.getLogger(__name__)
    
    logger.info("Supported calendar providers:")
    for provider in CalendarFactory.get_supported_providers():
        try:
            client_class = CalendarFactory.get_calendar_client_class(provider)
            logger.info(f"  - {provider}: {client_class.__name__}")
        except ValueError as e:
            logger.error(f"  - {provider}: Error - {e}")
    
    current_provider = EnvHelper.get_calendar_provider()
    logger.info(f"Currently configured provider: {current_provider}")


if __name__ == "__main__":
    # Example usage when running this file directly
    import asyncio
    import logging
    
    logging.basicConfig(level=logging.INFO)
    
    # Show provider comparison
    example_provider_comparison()
    
    # Run async examples
    async def main():
        print("\\n--- Example: Getting appointments for today ---")
        await example_get_appointments()
        
        print("\\n--- Example: Scheduling a test appointment ---")
        await example_schedule_appointment()
    
    asyncio.run(main())