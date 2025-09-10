"""
Calendar Provider Integration Example

This example demonstrates how to use different calendar providers
(Salesforce and Google Calendar) with the Prospect Incoming Callbot.
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add app to path for imports
sys.path.append(str(Path(__file__).parent.parent / 'app'))

from dotenv import load_dotenv

from agents.calendar_agent import CalendarAgent
from api_client.google_calendar_client import GoogleCalendarClient
from api_client.salesforce_api_client import SalesforceApiClient
from llms.langchain_factory import LangChainFactory
from llms.llm_info import LlmInfo
from utils.calendar_factory import CalendarFactory
from utils.envvar import EnvHelper

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def example_direct_google_calendar():
    """Example: Direct usage of Google Calendar client"""
    logger.info("=== Direct Google Calendar Client Example ===")
    
    try:
        # Create Google Calendar client directly
        calendar_client = GoogleCalendarClient()
        
        if not calendar_client.authenticate():
            logger.error("Failed to authenticate with Google Calendar")
            return
        
        # Test scheduling an appointment
        tomorrow = datetime.now() + timedelta(days=1)
        appointment_time = tomorrow.replace(hour=15, minute=0, second=0, microsecond=0)
        
        event_id = await calendar_client.schedule_new_appointment_async(
            subject="Direct Google Calendar Test",
            start_datetime=appointment_time.isoformat() + "Z",
            duration_minutes=45,
            description="Test appointment created directly via GoogleCalendarClient"
        )
        
        if event_id:
            logger.info(f"✓ Created appointment with ID: {event_id}")
            
            # Test retrieving appointments
            start_time = appointment_time.replace(hour=0, minute=0)
            end_time = appointment_time.replace(hour=23, minute=59)
            
            appointments = await calendar_client.get_scheduled_appointments_async(
                start_datetime=start_time.isoformat() + "Z",
                end_datetime=end_time.isoformat() + "Z"
            )
            
            logger.info(f"✓ Retrieved {len(appointments)} appointments")
            
            # Test deleting the appointment
            if await calendar_client.delete_event_by_id_async(event_id):
                logger.info("✓ Successfully deleted test appointment")
            else:
                logger.warning("⚠ Failed to delete test appointment")
        else:
            logger.error("✗ Failed to create appointment")
            
    except Exception as e:
        logger.error(f"Error in direct Google Calendar example: {e}")


async def example_direct_salesforce_calendar():
    """Example: Direct usage of Salesforce Calendar client"""
    logger.info("=== Direct Salesforce Calendar Client Example ===")
    
    try:
        # Create Salesforce client directly
        calendar_client = SalesforceApiClient()
        
        if not calendar_client.authenticate():
            logger.error("Failed to authenticate with Salesforce")
            return
        
        # Test scheduling an appointment
        tomorrow = datetime.now() + timedelta(days=1)
        appointment_time = tomorrow.replace(hour=16, minute=0, second=0, microsecond=0)
        
        event_id = await calendar_client.schedule_new_appointment_async(
            subject="Direct Salesforce Calendar Test",
            start_datetime=appointment_time.isoformat() + "Z",
            duration_minutes=30,
            description="Test appointment created directly via SalesforceApiClient"
        )
        
        if event_id:
            logger.info(f"✓ Created appointment with ID: {event_id}")
            
            # Test retrieving appointments
            start_time = appointment_time.replace(hour=0, minute=0)
            end_time = appointment_time.replace(hour=23, minute=59)
            
            appointments = await calendar_client.get_scheduled_appointments_async(
                start_datetime=start_time.isoformat() + "Z",
                end_datetime=end_time.isoformat() + "Z"
            )
            
            logger.info(f"✓ Retrieved {len(appointments)} appointments")
            
        else:
            logger.error("✗ Failed to create appointment")
            
    except Exception as e:
        logger.error(f"Error in direct Salesforce Calendar example: {e}")


async def example_calendar_factory():
    """Example: Using CalendarFactory for provider-agnostic calendar operations"""
    logger.info("=== Calendar Factory Example ===")
    
    try:
        # Get current provider configuration
        current_provider = EnvHelper.get_calendar_provider()
        logger.info(f"Current calendar provider: {current_provider}")
        
        # Create calendar client using factory
        calendar_client = CalendarFactory.create_calendar_client()
        logger.info(f"Created calendar client: {type(calendar_client).__name__}")
        
        # Test appointment scheduling (provider-agnostic)
        tomorrow = datetime.now() + timedelta(days=1)
        appointment_time = tomorrow.replace(hour=14, minute=30, second=0, microsecond=0)
        
        event_id = await calendar_client.schedule_new_appointment_async(
            subject=f"Factory Test ({current_provider})",
            start_datetime=appointment_time.isoformat() + "Z",
            duration_minutes=60,
            description=f"Test appointment created via CalendarFactory using {current_provider} provider"
        )
        
        if event_id:
            logger.info(f"✓ Created appointment with ID: {event_id}")
        else:
            logger.error("✗ Failed to create appointment")
            
    except Exception as e:
        logger.error(f"Error in calendar factory example: {e}")


async def example_calendar_agent_integration():
    """Example: Using calendar providers with CalendarAgent"""
    logger.info("=== Calendar Agent Integration Example ===")
    
    try:
        # Create calendar client using factory
        calendar_client = CalendarFactory.create_calendar_client()
        
        # Create LLM for CalendarAgent
        langchain_factory = LangChainFactory()
        llm_info = LlmInfo(provider="openai", model="gpt-3.5-turbo")
        classifier_llm = langchain_factory.create_langchain_llm(llm_info)
        
        # Create CalendarAgent with the calendar client
        calendar_agent = CalendarAgent(
            salesforce_api_client=calendar_client,  # CalendarAgent accepts CalendarClientInterface
            classifier_llm=classifier_llm
        )
        
        # Test calendar agent functionality
        user_input = "Je voudrais prendre rendez-vous demain à 14h"
        
        response = await calendar_agent.run_async(user_input)
        logger.info(f"Calendar agent response: {response}")
        
    except Exception as e:
        logger.error(f"Error in calendar agent integration example: {e}")


def example_provider_comparison():
    """Example: Comparing different calendar providers"""
    logger.info("=== Provider Comparison Example ===")
    
    logger.info("Supported calendar providers:")
    for provider in CalendarFactory.get_supported_providers():
        try:
            client_class = CalendarFactory.get_calendar_client_class(provider)
            logger.info(f"  ✓ {provider}: {client_class.__name__}")
            
            # Show provider-specific features
            if provider == "google":
                logger.info("    - Uses Google Calendar API v3")
                logger.info("    - Requires service account credentials")
                logger.info("    - Supports multiple calendars")
                logger.info("    - Limited appointment slot functionality")
            elif provider == "salesforce":
                logger.info("    - Uses Salesforce Events API")
                logger.info("    - Supports Lightning Scheduler")
                logger.info("    - Integrated with CRM data")
                logger.info("    - Native appointment slot support")
                
        except ValueError as e:
            logger.error(f"  ✗ {provider}: {e}")
    
    current_provider = EnvHelper.get_calendar_provider()
    logger.info(f"Currently configured provider: {current_provider}")


async def main():
    """Run all examples"""
    logger.info("Starting Calendar Provider Examples")
    
    # Show provider comparison
    example_provider_comparison()
    print()
    
    # Run provider-agnostic example
    await example_calendar_factory()
    print()
    
    # Run calendar agent integration example
    await example_calendar_agent_integration()
    print()
    
    # Run provider-specific examples based on configuration
    current_provider = EnvHelper.get_calendar_provider().lower()
    
    if current_provider == "google":
        await example_direct_google_calendar()
    elif current_provider == "salesforce":
        await example_direct_salesforce_calendar()
    else:
        logger.warning(f"Unknown provider '{current_provider}'. Skipping provider-specific examples.")
    
    logger.info("All examples completed")


if __name__ == "__main__":
    print("Calendar Provider Integration Examples")
    print("=====================================")
    print()
    print("This example demonstrates:")
    print("1. Direct usage of calendar providers")
    print("2. Provider-agnostic operations via CalendarFactory")
    print("3. Integration with CalendarAgent")
    print("4. Provider comparison and features")
    print()
    
    # Check configuration
    provider = EnvHelper.get_calendar_provider()
    print(f"Current configuration: CALENDAR_PROVIDER={provider}")
    print()
    
    # Run examples
    asyncio.run(main())