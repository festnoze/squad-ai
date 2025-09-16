# Google Calendar Integration Setup

This guide explains how to set up Google Calendar integration for the Prospect Incoming Callbot.

## Prerequisites

- Google Cloud Platform account
- Google Calendar API enabled
- Service account with Calendar API permissions

## Step 1: Enable Google Calendar API

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Select or create a project
3. Navigate to "APIs & Services" > "Library"
4. Search for "Google Calendar API"
5. Click on "Google Calendar API" and press "ENABLE"

## Step 2: Create a Service Account

1. In the Google Cloud Console, go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "Service Account"
3. Fill in the service account details:
   - **Name**: `callbot-calendar-service`
   - **Description**: `Service account for Prospect Incoming Callbot calendar operations`
4. Click "Create and Continue"
5. Grant the service account the "Editor" role (or create a custom role with Calendar permissions)
6. Click "Continue" and then "Done"

## Step 3: Generate Service Account Key

1. In the "Credentials" page, find your newly created service account
2. Click on the service account email
3. Go to the "Keys" tab
4. Click "Add Key" > "Create new key"
5. Select "JSON" format
6. Click "Create" - this will download the JSON key file

## Step 4: Configure the Callbot Application

1. **Place the credentials file**:
   ```bash
   # Create the secrets directory if it doesn't exist
   mkdir -p secrets/
   
   # Copy your downloaded JSON file
   cp path/to/your/downloaded-key.json secrets/google-calendar-service-account.json
   ```

2. **Update environment variables**:
   Edit your `.env` file to include:
   ```env
   # Choose Google Calendar as the provider
   CALENDAR_PROVIDER=google
   
   # Path to the service account credentials
   GOOGLE_CALENDAR_CREDENTIALS_FILEPATH=secrets/google-calendar-service-account.json
   
   # Calendar ID (use "primary" for the primary calendar, or specific calendar ID)
   GOOGLE_CALENDAR_ID=primary
   
   # Timezone for appointments
   GOOGLE_CALENDAR_TIMEZONE=Europe/Paris
   ```

## Step 5: Grant Calendar Access (Optional)

If you want to use a specific Google Calendar (not the service account's own calendar):

1. Go to [Google Calendar](https://calendar.google.com/)
2. Find the calendar you want to use
3. Click the three dots next to the calendar name
4. Select "Settings and sharing"
5. In the "Share with specific people" section, add your service account email
6. Grant "Make changes to events" permission
7. Copy the Calendar ID from the "Integrate calendar" section if using a specific calendar

## Step 6: Test the Configuration

You can test the Google Calendar integration using the provided examples:

```python
# Test in Python
import asyncio
import sys
sys.path.append('app')

from utils.calendar_factory import CalendarFactory, example_get_appointments

async def test_google_calendar():
    # This will use Google Calendar if CALENDAR_PROVIDER=google
    calendar_client = CalendarFactory.create_calendar_client()
    
    # Test authentication
    if calendar_client.authenticate():
        print("✓ Google Calendar authentication successful")
        
        # Test getting appointments
        appointments = await example_get_appointments()
        print(f"Found {len(appointments)} appointments")
    else:
        print("✗ Google Calendar authentication failed")

# Run the test
asyncio.run(test_google_calendar())
```

## Troubleshooting

### Common Issues

1. **Authentication Error**: 
   - Verify the JSON credentials file path is correct
   - Ensure the service account has the necessary permissions
   - Check that the Google Calendar API is enabled

2. **Calendar Not Found**:
   - If using a specific calendar ID, ensure the service account has access
   - Try using "primary" as the calendar ID first

3. **Permission Denied**:
   - Verify the service account has "Editor" role or Calendar permissions
   - If using a shared calendar, ensure proper sharing permissions

4. **Invalid Credentials**:
   - Re-download the service account key file
   - Ensure the JSON file is valid and not corrupted

### Logging

Enable debug logging to see detailed error messages:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Security Notes

- **Never commit the service account JSON file to version control**
- Store credentials securely in production environments
- Consider using environment-specific service accounts
- Regularly rotate service account keys
- Use the principle of least privilege for permissions

## Calendar Limitations

Compared to Salesforce Calendar, Google Calendar has some limitations:

- No native "appointment slots" functionality (implemented via available time detection)
- No Lightning Scheduler equivalent
- Different event metadata structure
- No built-in CRM integration

These limitations are handled by the `GoogleCalendarClient` implementation to maintain compatibility with the `CalendarClientInterface`.