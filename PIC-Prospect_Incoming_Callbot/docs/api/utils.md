# Utils API Reference

The PIC Prospect Incoming Callbot includes various utility modules that provide helper functions, configuration management, and support functionality. This document provides detailed API reference for all utility components.

## Environment Variable Management

### EnvVar Utilities

**File**: `app/utils/envvar.py`

**Purpose**: Centralized environment variable management with validation and type conversion

```python
class EnvVar:
    @staticmethod
    def get_required(key: str, var_type: type = str) -> Any:
        """Get required environment variable with type conversion"""

    @staticmethod
    def get_optional(key: str, default: Any = None, var_type: type = str) -> Any:
        """Get optional environment variable with default value"""

    @staticmethod
    def get_boolean(key: str, default: bool = False) -> bool:
        """Get boolean environment variable"""

    @staticmethod
    def get_list(key: str, separator: str = ",", default: List[str] = None) -> List[str]:
        """Get list from comma-separated environment variable"""

    @staticmethod
    def validate_all_required() -> Dict[str, str]:
        """Validate all required environment variables are present"""
```

#### Key Environment Variables

```python
# Core application settings
ENVIRONMENT = EnvVar.get_optional("ENVIRONMENT", "development")
HOST = EnvVar.get_optional("HOST", "0.0.0.0")
PORT = EnvVar.get_optional("PORT", 8344, int)

# Twilio configuration
TWILIO_ACCOUNT_SID = EnvVar.get_required("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = EnvVar.get_required("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = EnvVar.get_required("TWILIO_PHONE_NUMBER")

# Google Cloud configuration
GOOGLE_CLOUD_PROJECT = EnvVar.get_required("GOOGLE_CLOUD_PROJECT")
GOOGLE_APPLICATION_CREDENTIALS = EnvVar.get_optional("GOOGLE_APPLICATION_CREDENTIALS")

# Speech configuration
SPEECH_LANGUAGE = EnvVar.get_optional("SPEECH_LANGUAGE", "fr-FR")
SPEECH_MODEL = EnvVar.get_optional("SPEECH_MODEL", "chirp_3_hd")
TTS_VOICE_NAME = EnvVar.get_optional("TTS_VOICE_NAME", "fr-FR-Chirp3-HD-Zephyr")

# Calendar configuration
CALENDAR_PROVIDER = EnvVar.get_optional("CALENDAR_PROVIDER", "salesforce")
GOOGLE_CALENDAR_ID = EnvVar.get_optional("GOOGLE_CALENDAR_ID", "primary")
GOOGLE_CALENDAR_TIMEZONE = EnvVar.get_optional("GOOGLE_CALENDAR_TIMEZONE", "Europe/Paris")

# Salesforce configuration
SALESFORCE_USERNAME = EnvVar.get_required("SALESFORCE_USERNAME")
SALESFORCE_PASSWORD = EnvVar.get_required("SALESFORCE_PASSWORD")
SALESFORCE_SECURITY_TOKEN = EnvVar.get_required("SALESFORCE_SECURITY_TOKEN")
SALESFORCE_DOMAIN = EnvVar.get_optional("SALESFORCE_DOMAIN", "login")

# LLM configuration
OPENAI_API_KEY = EnvVar.get_optional("OPENAI_API_KEY")
ANTHROPIC_API_KEY = EnvVar.get_optional("ANTHROPIC_API_KEY")
LLM_PROVIDER = EnvVar.get_optional("LLM_PROVIDER", "openai")
LLM_MODEL = EnvVar.get_optional("LLM_MODEL", "gpt-4")

# Audio processing
VAD_MODE = EnvVar.get_optional("VAD_MODE", 2, int)
AUDIO_SAMPLE_RATE = EnvVar.get_optional("AUDIO_SAMPLE_RATE", 16000, int)
AUDIO_CHUNK_SIZE = EnvVar.get_optional("AUDIO_CHUNK_SIZE", 1024, int)
```

#### Validation Functions

```python
def validate_twilio_config() -> bool:
    """Validate Twilio configuration"""
    required_vars = [
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_PHONE_NUMBER"
    ]

    missing = []
    for var in required_vars:
        if not EnvVar.get_optional(var):
            missing.append(var)

    if missing:
        raise ValueError(f"Missing required Twilio environment variables: {', '.join(missing)}")

    return True

def validate_google_cloud_config() -> bool:
    """Validate Google Cloud configuration"""
    project_id = EnvVar.get_optional("GOOGLE_CLOUD_PROJECT")
    credentials_path = EnvVar.get_optional("GOOGLE_APPLICATION_CREDENTIALS")

    if not project_id:
        raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is required")

    if credentials_path and not Path(credentials_path).exists():
        raise ValueError(f"Google Cloud credentials file not found: {credentials_path}")

    return True

def validate_all_configurations() -> Dict[str, bool]:
    """Validate all service configurations"""
    validation_results = {}

    try:
        validation_results["twilio"] = validate_twilio_config()
    except ValueError as e:
        validation_results["twilio"] = str(e)

    try:
        validation_results["google_cloud"] = validate_google_cloud_config()
    except ValueError as e:
        validation_results["google_cloud"] = str(e)

    return validation_results
```

## Google Calendar Authentication

### Google Calendar Auth Helper

**File**: `app/utils/google_calendar_auth.py`

**Purpose**: Handle Google Calendar API authentication and authorization

```python
class GoogleCalendarAuth:
    def __init__(self, credentials_file: str, scopes: List[str]):
        self.credentials_file = credentials_file
        self.scopes = scopes
        self.service = None

    async def authenticate_async(self) -> Resource:
        """Authenticate and return Google Calendar service"""

    async def refresh_credentials_async(self) -> bool:
        """Refresh authentication credentials"""

    def get_calendar_service(self) -> Resource:
        """Get authenticated Google Calendar service"""
```

#### Authentication Methods

```python
def create_service_account_credentials(credentials_file: str, scopes: List[str]) -> service_account.Credentials:
    """Create service account credentials from JSON file"""
    try:
        credentials = service_account.Credentials.from_service_account_file(
            credentials_file,
            scopes=scopes
        )
        return credentials
    except Exception as e:
        logger.error(f"Failed to create service account credentials: {e}")
        raise ValueError(f"Invalid Google service account credentials: {e}")

def build_calendar_service(credentials: service_account.Credentials) -> Resource:
    """Build Google Calendar API service"""
    try:
        service = build('calendar', 'v3', credentials=credentials)
        return service
    except Exception as e:
        logger.error(f"Failed to build Calendar service: {e}")
        raise ValueError(f"Failed to initialize Google Calendar API: {e}")

async def test_calendar_access_async(service: Resource, calendar_id: str = "primary") -> bool:
    """Test calendar access with current credentials"""
    try:
        # Try to get calendar information
        calendar = service.calendars().get(calendarId=calendar_id).execute()
        logger.info(f"Successfully accessed calendar: {calendar.get('summary', 'Unknown')}")
        return True
    except Exception as e:
        logger.error(f"Calendar access test failed: {e}")
        return False
```

#### Setup Helper Functions

```python
async def setup_google_calendar_async(
    credentials_file: str,
    calendar_id: str = "primary",
    timezone: str = "UTC"
) -> GoogleCalendarAuth:
    """Setup Google Calendar authentication"""

    # Validate credentials file
    if not Path(credentials_file).exists():
        raise FileNotFoundError(f"Google Calendar credentials file not found: {credentials_file}")

    # Define required scopes
    scopes = [
        'https://www.googleapis.com/auth/calendar',
        'https://www.googleapis.com/auth/calendar.events'
    ]

    # Create auth helper
    auth_helper = GoogleCalendarAuth(credentials_file, scopes)

    # Test authentication
    service = await auth_helper.authenticate_async()
    access_test = await test_calendar_access_async(service, calendar_id)

    if not access_test:
        raise ValueError("Failed to access Google Calendar with provided credentials")

    logger.info("Google Calendar authentication setup completed successfully")
    return auth_helper

def generate_service_account_setup_instructions() -> str:
    """Generate setup instructions for Google service account"""
    instructions = """
    Google Calendar Service Account Setup:

    1. Go to Google Cloud Console (https://console.cloud.google.com)
    2. Create a new project or select existing project
    3. Enable the Google Calendar API:
       - Go to "APIs & Services" > "Library"
       - Search for "Google Calendar API"
       - Click "Enable"

    4. Create a service account:
       - Go to "APIs & Services" > "Credentials"
       - Click "Create Credentials" > "Service Account"
       - Fill in service account details
       - Click "Create and Continue"

    5. Download credentials:
       - In the service account list, click on your service account
       - Go to "Keys" tab
       - Click "Add Key" > "Create new key"
       - Choose JSON format and download

    6. Share calendar with service account:
       - Open Google Calendar
       - Go to calendar settings
       - Under "Share with specific people", add the service account email
       - Grant "Make changes and manage sharing" permission

    7. Set environment variables:
       - GOOGLE_CALENDAR_CREDENTIALS_FILEPATH=path/to/credentials.json
       - GOOGLE_CALENDAR_ID=your_calendar_id (or "primary" for main calendar)
       - GOOGLE_CALENDAR_TIMEZONE=your_timezone (e.g., "Europe/Paris")
    """
    return instructions
```

## Configuration Management

### Configuration Models

**File**: `app/utils/config_models.py`

**Purpose**: Pydantic models for configuration validation

```python
class AudioConfig(BaseModel):
    sample_rate: int = 16000
    chunk_size: int = 1024
    max_buffer_duration: int = 30  # seconds
    vad_mode: int = 2  # WebRTC VAD mode (0-3)
    language_code: str = "fr-FR"
    speech_model: str = "chirp_3_hd"

class VoiceConfig(BaseModel):
    voice_name: str = "fr-FR-Chirp3-HD-Zephyr"
    language_code: str = "fr-FR"
    speaking_rate: float = 1.0
    pitch: float = 0.0
    volume_gain_db: float = 0.0

class TwilioConfig(BaseModel):
    account_sid: str
    auth_token: str
    phone_number: str
    webhook_base_url: Optional[str] = None

class GoogleCloudConfig(BaseModel):
    project_id: str
    credentials_file: Optional[str] = None
    speech_config: AudioConfig = AudioConfig()
    tts_config: VoiceConfig = VoiceConfig()

class CalendarConfig(BaseModel):
    provider: Literal["google", "salesforce"] = "salesforce"
    google_calendar_id: str = "primary"
    google_credentials_file: Optional[str] = None
    timezone: str = "UTC"

class SalesforceConfig(BaseModel):
    username: str
    password: str
    security_token: str
    domain: str = "login"
    api_version: str = "58.0"

class ApplicationConfig(BaseModel):
    environment: Literal["development", "production"] = "development"
    host: str = "0.0.0.0"
    port: int = 8344
    debug: bool = False
    log_level: str = "INFO"

    # Service configurations
    twilio: TwilioConfig
    google_cloud: GoogleCloudConfig
    calendar: CalendarConfig
    salesforce: SalesforceConfig
```

### Configuration Loader

```python
class ConfigLoader:
    @staticmethod
    def load_from_env() -> ApplicationConfig:
        """Load configuration from environment variables"""
        try:
            config = ApplicationConfig(
                environment=EnvVar.get_optional("ENVIRONMENT", "development"),
                host=EnvVar.get_optional("HOST", "0.0.0.0"),
                port=EnvVar.get_optional("PORT", 8344, int),
                debug=EnvVar.get_boolean("DEBUG", False),
                log_level=EnvVar.get_optional("LOG_LEVEL", "INFO"),

                twilio=TwilioConfig(
                    account_sid=EnvVar.get_required("TWILIO_ACCOUNT_SID"),
                    auth_token=EnvVar.get_required("TWILIO_AUTH_TOKEN"),
                    phone_number=EnvVar.get_required("TWILIO_PHONE_NUMBER"),
                    webhook_base_url=EnvVar.get_optional("TWILIO_WEBHOOK_BASE_URL")
                ),

                google_cloud=GoogleCloudConfig(
                    project_id=EnvVar.get_required("GOOGLE_CLOUD_PROJECT"),
                    credentials_file=EnvVar.get_optional("GOOGLE_APPLICATION_CREDENTIALS")
                ),

                calendar=CalendarConfig(
                    provider=EnvVar.get_optional("CALENDAR_PROVIDER", "salesforce"),
                    google_calendar_id=EnvVar.get_optional("GOOGLE_CALENDAR_ID", "primary"),
                    google_credentials_file=EnvVar.get_optional("GOOGLE_CALENDAR_CREDENTIALS_FILEPATH"),
                    timezone=EnvVar.get_optional("GOOGLE_CALENDAR_TIMEZONE", "UTC")
                ),

                salesforce=SalesforceConfig(
                    username=EnvVar.get_required("SALESFORCE_USERNAME"),
                    password=EnvVar.get_required("SALESFORCE_PASSWORD"),
                    security_token=EnvVar.get_required("SALESFORCE_SECURITY_TOKEN"),
                    domain=EnvVar.get_optional("SALESFORCE_DOMAIN", "login"),
                    api_version=EnvVar.get_optional("SALESFORCE_API_VERSION", "58.0")
                )
            )

            return config

        except ValidationError as e:
            logger.error(f"Configuration validation failed: {e}")
            raise ValueError(f"Invalid configuration: {e}")

    @staticmethod
    def validate_config(config: ApplicationConfig) -> List[str]:
        """Validate configuration and return list of issues"""
        issues = []

        # Validate file paths
        if config.google_cloud.credentials_file:
            if not Path(config.google_cloud.credentials_file).exists():
                issues.append(f"Google Cloud credentials file not found: {config.google_cloud.credentials_file}")

        if config.calendar.google_credentials_file:
            if not Path(config.calendar.google_credentials_file).exists():
                issues.append(f"Google Calendar credentials file not found: {config.calendar.google_credentials_file}")

        # Validate Twilio phone number format
        if not config.twilio.phone_number.startswith('+'):
            issues.append("Twilio phone number should start with '+'")

        # Validate timezone
        try:
            pytz.timezone(config.calendar.timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            issues.append(f"Unknown timezone: {config.calendar.timezone}")

        return issues
```

## Logging Utilities

### Logging Configuration

**File**: `app/utils/logging_config.py`

**Purpose**: Configure application logging with structured output

```python
def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    enable_json_logging: bool = False
) -> None:
    """Setup application logging configuration"""

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
            },
            "detailed": {
                "format": "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s"
            },
            "json": {
                "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                "format": "%(asctime)s %(name)s %(levelname)s %(message)s"
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "standard",
                "stream": "ext://sys.stdout"
            }
        },
        "loggers": {
            "app": {
                "level": log_level,
                "handlers": ["console"],
                "propagate": False
            },
            "uvicorn": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False
            }
        },
        "root": {
            "level": log_level,
            "handlers": ["console"]
        }
    }

    # Add file handler if log file specified
    if log_file:
        logging_config["handlers"]["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": log_level,
            "formatter": "json" if enable_json_logging else "detailed",
            "filename": log_file,
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5
        }

        # Add file handler to all loggers
        for logger_name in ["app", "uvicorn", "root"]:
            logging_config["loggers"][logger_name]["handlers"].append("file")

    dictConfig(logging_config)

def get_call_logger(call_id: str) -> logging.Logger:
    """Get logger with call ID context"""
    logger = logging.getLogger(f"app.call.{call_id}")
    return logger

def log_performance_metric(
    operation: str,
    duration: float,
    success: bool = True,
    additional_data: Optional[Dict] = None
) -> None:
    """Log performance metric"""
    logger = logging.getLogger("app.performance")

    log_data = {
        "operation": operation,
        "duration_ms": round(duration * 1000, 2),
        "success": success
    }

    if additional_data:
        log_data.update(additional_data)

    logger.info("Performance metric", extra=log_data)
```

## Helper Functions

### Text Processing Utilities

```python
def clean_text_for_tts(text: str) -> str:
    """Clean text for text-to-speech processing"""
    # Remove or replace problematic characters
    text = re.sub(r'[^\w\s\.,!?;:()\-]', '', text)

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    # Handle common abbreviations
    abbreviations = {
        'M.': 'Monsieur',
        'Mme': 'Madame',
        'Dr': 'Docteur',
        'etc.': 'et cetera'
    }

    for abbrev, full_form in abbreviations.items():
        text = text.replace(abbrev, full_form)

    return text

def extract_phone_number(text: str) -> Optional[str]:
    """Extract phone number from text"""
    # French phone number patterns
    patterns = [
        r'\b0[1-9](?:[-.\s]?\d{2}){4}\b',  # 01.02.03.04.05
        r'\b\+33[1-9](?:[-.\s]?\d{2}){4}\b',  # +33.1.02.03.04.05
        r'\b(?:0033)[1-9](?:[-.\s]?\d{2}){4}\b'  # 0033.1.02.03.04.05
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            # Normalize phone number
            phone = re.sub(r'[-.\s]', '', match.group())
            return phone

    return None

def validate_email(email: str) -> bool:
    """Validate email address format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))
```

### Date and Time Utilities

```python
def parse_french_date(date_string: str) -> Optional[datetime]:
    """Parse French date format to datetime"""
    french_date_patterns = [
        '%d/%m/%Y',
        '%d-%m-%Y',
        '%d %m %Y',
        '%d/%m/%Y %H:%M',
        '%d-%m-%Y %H:%M'
    ]

    for pattern in french_date_patterns:
        try:
            return datetime.strptime(date_string, pattern)
        except ValueError:
            continue

    return None

def format_duration(seconds: int) -> str:
    """Format duration in seconds to human readable format"""
    if seconds < 60:
        return f"{seconds} secondes"
    elif seconds < 3600:
        minutes = seconds // 60
        remaining_seconds = seconds % 60
        if remaining_seconds == 0:
            return f"{minutes} minutes"
        return f"{minutes} minutes et {remaining_seconds} secondes"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours} heures et {minutes} minutes"

def get_business_hours(timezone_str: str = "Europe/Paris") -> Tuple[time, time]:
    """Get business hours for timezone"""
    # Default business hours: 9 AM to 6 PM
    start_time = time(9, 0)
    end_time = time(18, 0)

    return start_time, end_time

def is_business_hours(
    check_datetime: datetime,
    timezone_str: str = "Europe/Paris"
) -> bool:
    """Check if datetime falls within business hours"""
    tz = pytz.timezone(timezone_str)
    localized_dt = check_datetime.astimezone(tz)

    start_time, end_time = get_business_hours(timezone_str)

    # Check if it's a weekday (Monday = 0, Sunday = 6)
    if localized_dt.weekday() > 4:  # Saturday or Sunday
        return False

    # Check if within business hours
    current_time = localized_dt.time()
    return start_time <= current_time <= end_time
```

These utility functions provide essential support functionality for the entire callbot application, ensuring consistent configuration management, authentication handling, and text processing across all components.