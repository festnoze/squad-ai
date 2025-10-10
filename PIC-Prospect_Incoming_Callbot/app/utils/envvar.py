# /!\ 'load_dotenv()'  Must be done beforehand in the main script!
import os

from dotenv import load_dotenv


class EnvHelper:
    is_env_loaded = False

    @staticmethod
    def get_openai_api_key() -> str:
        return EnvHelper.get_env_variable_value_by_name("OPENAI_API_KEY") or ""

    @staticmethod
    def get_salesforce_username() -> str:
        return EnvHelper.get_env_variable_value_by_name("SALESFORCE_USERNAME", fails_if_missing=False) or ""

    @staticmethod
    def get_salesforce_password() -> str:
        return EnvHelper.get_env_variable_value_by_name("SALESFORCE_PASSWORD", fails_if_missing=False) or ""

    @staticmethod
    def get_salesforce_client_secret() -> str:
        return EnvHelper.get_env_variable_value_by_name("SALESFORCE_CLIENT_SECRET", fails_if_missing=False) or ""

    @staticmethod
    def get_salesforce_private_key_file() -> str:
        return EnvHelper.get_env_variable_value_by_name("SALESFORCE_PRIVATE_KEY_FILE", fails_if_missing=False) or ""

    @staticmethod
    def get_salesforce_consumer_key() -> str:
        return EnvHelper.get_env_variable_value_by_name("SALESFORCE_CONSUMER_KEY", fails_if_missing=False) or ""

    @staticmethod
    def get_salesforce_auth_method() -> str:
        return EnvHelper.get_env_variable_value_by_name("SALESFORCE_AUTH_METHOD", fails_if_missing=False) or "password"

    @staticmethod
    def get_salesforce_owner_strategy() -> str:
        """
        Get the Salesforce owner retrieval strategy.

        Returns:
            str: The strategy to use for retrieving owner information.
                 - "both": Try opportunity owner first, fallback to contact owner (default)
                 - "opport_only": Only use opportunity owner, no fallback
                 - "direct_only": Only use direct contact owner, skip opportunities
        """
        strategy = EnvHelper.get_env_variable_value_by_name("SALESFORCE_OWNER_STRATEGY", fails_if_missing=False) or "both"
        valid_strategies = ["both", "opport_only", "direct_only"]
        if strategy.lower() not in valid_strategies:
            # Log warning and default to "both"
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Invalid SALESFORCE_OWNER_STRATEGY '{strategy}'. Valid values: {valid_strategies}. Defaulting to 'both'.")
            return "both"
        return strategy.lower()

    @staticmethod
    def get_company_name() -> str:
        return EnvHelper.get_env_variable_value_by_name("COMPANY_NAME", fails_if_missing=False) or "Studi"

    @staticmethod
    def get_rag_api_host() -> str:
        return EnvHelper.get_env_variable_value_by_name("RAG_API_HOST", fails_if_missing=False) or ""

    @staticmethod
    def get_rag_api_port() -> int:
        port_str = EnvHelper.get_env_variable_value_by_name("RAG_API_PORT", fails_if_missing=False)
        return int(port_str) if port_str else 0

    @staticmethod
    def get_rag_api_is_ssh() -> bool:
        value = EnvHelper.get_env_variable_value_by_name("RAG_API_IS_SSH", fails_if_missing=False)
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_rag_api_connect_timeout() -> float:
        """Get RAG API connect timeout in seconds (default: 10.0)"""
        value = EnvHelper.get_env_variable_value_by_name("RAG_API_CONNECT_TIMEOUT", fails_if_missing=False)
        return float(value) if value else 10.0

    @staticmethod
    def get_rag_api_read_timeout() -> float:
        """Get RAG API read timeout in seconds (default: 80.0)"""
        value = EnvHelper.get_env_variable_value_by_name("RAG_API_READ_TIMEOUT", fails_if_missing=False)
        return float(value) if value else 80.0

    @staticmethod
    def get_rag_api_test_timeout() -> float:
        """Get RAG API test connection timeout in seconds (default: 10.0)"""
        value = EnvHelper.get_env_variable_value_by_name("RAG_API_TEST_TIMEOUT", fails_if_missing=False)
        return float(value) if value else 10.0

    @staticmethod
    def get_salesforce_use_lightning_scheduler() -> bool:
        """Get whether to use Lightning Scheduler instead of Events (default: False)"""
        value = EnvHelper.get_env_variable_value_by_name("SALESFORCE_USE_LIGHTNING_SCHEDULER", fails_if_missing=False)
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_salesforce_default_work_type_id() -> str | None:
        """Get default Work Type ID for Lightning Scheduler appointments"""
        return EnvHelper.get_env_variable_value_by_name("SALESFORCE_DEFAULT_WORK_TYPE_ID", fails_if_missing=False)

    @staticmethod
    def get_salesforce_default_service_territory_id() -> str | None:
        """Get default Service Territory ID for Lightning Scheduler appointments"""
        return EnvHelper.get_env_variable_value_by_name("SALESFORCE_DEFAULT_SERVICE_TERRITORY_ID", fails_if_missing=False)

    @staticmethod
    def get_python_paths() -> list[str]:
        paths = EnvHelper.get_env_variable_value_by_name("PYTHONPATH", fails_if_missing=False) or ""
        return paths.split(";")

    @staticmethod
    def get_do_audio_preprocessing() -> bool:
        value = EnvHelper.get_env_variable_value_by_name("DO_AUDIO_PREPROCESSING", fails_if_missing=False)
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_keep_incoming_audio_files() -> bool:
        value = EnvHelper.get_env_variable_value_by_name("KEEP_INCOMING_AUDIO_FILES", fails_if_missing=False)
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_keep_outgoing_audio_file() -> bool:
        value = EnvHelper.get_env_variable_value_by_name("KEEP_OUTGOING_AUDIO_FILES", fails_if_missing=False)
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_text_to_speech_provider() -> str:
        return EnvHelper.get_env_variable_value_by_name("TEXT_TO_SPEECH_PROVIDER", fails_if_missing=False) or ""

    @staticmethod
    def get_text_to_speech_voice() -> str:
        return EnvHelper.get_env_variable_value_by_name("TEXT_TO_SPEECH_VOICE", fails_if_missing=False) or ""

    @staticmethod
    def get_text_to_speech_instructions() -> str:
        return EnvHelper.get_env_variable_value_by_name("TEXT_TO_SPEECH_INSTRUCTIONS", fails_if_missing=False) or ""

    @staticmethod
    def get_text_to_speech_model() -> str:
        return EnvHelper.get_env_variable_value_by_name("TEXT_TO_SPEECH_MODEL", fails_if_missing=False) or ""

    @staticmethod
    def get_speech_to_text_provider() -> str:
        return EnvHelper.get_env_variable_value_by_name("SPEECH_TO_TEXT_PROVIDER", fails_if_missing=False) or ""

    @staticmethod
    def get_can_speech_be_interupted() -> bool:
        value = EnvHelper.get_env_variable_value_by_name("CAN_SPEECH_BE_INTERUPTED", fails_if_missing=False) or ""
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_twilio_sid() -> str:
        return EnvHelper.get_env_variable_value_by_name("TWILIO_SID", fails_if_missing=False) or ""

    @staticmethod
    def get_twilio_auth() -> str:
        return EnvHelper.get_env_variable_value_by_name("TWILIO_AUTH", fails_if_missing=False) or ""

    @staticmethod
    def get_twilio_phone_number() -> str:
        return EnvHelper.get_env_variable_value_by_name("TWILIO_PHONE_NUMBER", fails_if_missing=False) or ""

    @staticmethod
    def get_telnyx_api_key() -> str:
        return EnvHelper.get_env_variable_value_by_name("TELNYX_API_KEY", fails_if_missing=False) or ""

    @staticmethod
    def get_telnyx_profile_id() -> str:
        return EnvHelper.get_env_variable_value_by_name("TELNYX_PROFILE_ID", fails_if_missing=False) or ""

    @staticmethod
    def get_repeat_user_input() -> bool:
        value = EnvHelper.get_env_variable_value_by_name("REPEAT_USER_INPUT", fails_if_missing=False)
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_allow_test_fake_incoming_calls() -> bool:
        value = EnvHelper.get_env_variable_value_by_name("ALLOW_TEST_FAKE_INCOMING_CALLS", fails_if_missing=False)
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_test_call_count() -> int:
        value = EnvHelper.get_env_variable_value_by_name("TEST_CALL_COUNT", fails_if_missing=False)
        return int(value) if value else 1

    @staticmethod
    def get_available_actions() -> list[str]:
        actions: str = EnvHelper.get_env_variable_value_by_name("AVAILABLE_ACTIONS", fails_if_missing=False) or ""
        return [action.strip() for action in actions.split(",")] if actions else []

    @staticmethod
    def get_waiting_music_on_calendar() -> bool:
        value = EnvHelper.get_env_variable_value_by_name("WAITING_MUSIC_ON_CALENDAR", fails_if_missing=False)
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_waiting_music_on_rag() -> bool:
        value = EnvHelper.get_env_variable_value_by_name("WAITING_MUSIC_ON_RAG", fails_if_missing=False)
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_waiting_music_increasing_volume_duration() -> float:
        value = EnvHelper.get_env_variable_value_by_name("WAITING_MUSIC_INCREASING_VOLUME_DURATION", fails_if_missing=False)
        return float(value) if value else 0.0

    @staticmethod
    def get_waiting_music_start_delay() -> float:
        value = EnvHelper.get_env_variable_value_by_name("WAITING_MUSIC_START_DELAY", fails_if_missing=False)
        return float(value) if value else 0.0

    @staticmethod
    def get_background_noise_enabled() -> bool:
        value = EnvHelper.get_env_variable_value_by_name("BACKGROUND_NOISE_ENABLED", fails_if_missing=False)
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_background_noise_volume() -> float:
        value = EnvHelper.get_env_variable_value_by_name("BACKGROUND_NOISE_VOLUME", fails_if_missing=False)
        return float(value) if value else 0.1

    @staticmethod
    def get_perform_background_noise_calibration() -> bool:
        value = EnvHelper.get_env_variable_value_by_name("PERFORM_BACKGROUND_NOISE_CALIBRATION", fails_if_missing=False)
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_speech_threshold() -> int:
        value = EnvHelper.get_env_variable_value_by_name("SPEECH_THRESHOLD", fails_if_missing=False)
        return int(value) if value else 500

    @staticmethod
    def get_required_silence_ms_to_answer() -> int:
        value = EnvHelper.get_env_variable_value_by_name("REQUIRED_SILENCE_MS_TO_ANSWER", fails_if_missing=False)
        return int(value) if value else 700

    @staticmethod
    def get_min_audio_bytes_for_processing() -> int:
        value = EnvHelper.get_env_variable_value_by_name("MIN_AUDIO_BYTES_FOR_PROCESSING", fails_if_missing=False)
        return int(value) if value else 1000

    @staticmethod
    def get_max_audio_bytes_for_processing() -> int:
        value = EnvHelper.get_env_variable_value_by_name("MAX_AUDIO_BYTES_FOR_PROCESSING", fails_if_missing=False)
        return int(value) if value else 200000

    @staticmethod
    def get_max_silence_duration_before_reasking() -> int:
        value = EnvHelper.get_env_variable_value_by_name("MAX_SILENCE_DURATION_BEFORE_REASKING", fails_if_missing=False)
        return int(value) if value else 15000

    @staticmethod
    def get_max_silence_duration_before_hangup() -> int:
        value = EnvHelper.get_env_variable_value_by_name("MAX_SILENCE_DURATION_BEFORE_HANGUP", fails_if_missing=False)
        return int(value) if value else 70000

    @staticmethod
    def get_max_consecutive_errors() -> int:
        value = EnvHelper.get_env_variable_value_by_name("MAX_CONSECUTIVE_ERRORS", fails_if_missing=False)
        return int(value) if value else 3

    @staticmethod
    def get_speak_anew_on_long_silence() -> bool:
        value = EnvHelper.get_env_variable_value_by_name("SPEAK_ANEW_ON_LONG_SILENCE", fails_if_missing=False)
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_google_credentials_filepath() -> str:
        return EnvHelper.get_env_variable_value_by_name("GOOGLE_CREDENTIALS_FILEPATH") or ""

    @staticmethod
    def get_do_acknowledge_user_speech() -> bool:
        value = EnvHelper.get_env_variable_value_by_name("DO_ACKNOWLEDGE_USER_SPEECH", fails_if_missing=False)
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_long_acknowledgement() -> bool:
        value = EnvHelper.get_env_variable_value_by_name("LONG_ACKNOWLEDGEMENT", fails_if_missing=False)
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_conversation_persistence_type() -> str:
        return EnvHelper.get_env_variable_value_by_name("CONVERSATION_PERSISTENCE_TYPE", fails_if_missing=False) or "no"

    @staticmethod
    def get_admin_api_keys() -> list[str]:
        """Get the list of allowed API keys for admin endpoints"""
        keys_str = EnvHelper.get_env_variable_value_by_name("ADMIN_API_KEYS", fails_if_missing=False)
        return [key.strip() for key in keys_str.split(",")] if keys_str else []

    @staticmethod
    def is_valid_admin_api_key(api_key: str) -> bool:
        """Check if the provided API key is valid for admin operations"""
        allowed_keys = EnvHelper.get_admin_api_keys()
        return api_key in allowed_keys and len(allowed_keys) > 0

    @staticmethod
    def load_all_env_var(force_load_from_env_file: bool = False):
        if not EnvHelper.is_env_loaded or force_load_from_env_file:
            load_dotenv()
            EnvHelper._load_custom_env_files()
            EnvHelper.is_env_loaded = True

    ### Internal methods###
    #######################

    @staticmethod
    def _get_custom_env_files() -> str:
        return EnvHelper.get_env_variable_value_by_name("CUSTOM_ENV_FILES", load_env=False, fails_if_missing=False) or ""

    @staticmethod
    def _get_llms_json() -> str:
        return EnvHelper.get_env_variable_value_by_name("LLMS_JSON") or ""

    @staticmethod
    def _load_custom_env_files():
        custom_env_files = EnvHelper._get_custom_env_files()

        # In case no custom additionnal env. files are defined into a 'CUSTOM_ENV_FILES' key of the '.env' file
        if not custom_env_files:
            return

        custom_env_filenames = [filename.strip() for filename in custom_env_files.split(",")]
        for custom_env_filename in custom_env_filenames:
            if not os.path.exists(custom_env_filename):
                raise FileNotFoundError(f"/!\\ Environment file: '{custom_env_filename}' was not found at the project root.")
            load_dotenv(custom_env_filename)

    @staticmethod
    def get_env_variable_value_by_name(variable_name: str, load_env: bool = True, fails_if_missing: bool = True, remove_comments: bool = True, force_load_from_env_file: bool = False) -> str | None:
        if variable_name not in os.environ:
            if load_env:
                EnvHelper.load_all_env_var()
            variable_value: str | None = os.getenv(variable_name, None)
            if not variable_value:
                if fails_if_missing:
                    raise ValueError(f'Variable named: "{variable_name}" is not set in the environment')
                else:
                    return None
            os.environ[variable_name] = variable_value

        value = os.environ[variable_name]
        if remove_comments and "#" in value:
            value = value.split("#")[0].strip()

        return value

    @staticmethod
    def get_remove_logs_upon_startup() -> bool:
        value = EnvHelper.get_env_variable_value_by_name("REMOVE_LOGS_UPON_STARTUP", fails_if_missing=False)
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_serve_documentation() -> bool:
        """
        Get whether to serve MkDocs documentation alongside the API.

        Returns:
            bool: True if documentation should be served at /docs-site/, False otherwise.
                  Defaults to True for development, False for production.
        """
        value = EnvHelper.get_env_variable_value_by_name("SERVE_DOCUMENTATION", fails_if_missing=False)
        if value is not None:
            return value.lower() == "true"

        # Default behavior: serve docs in development, not in production
        environment = EnvHelper.get_env_variable_value_by_name("ENVIRONMENT", fails_if_missing=False) or "development"
        return environment.lower() == "development"

    # Latency tracking configuration methods
    @staticmethod
    def get_latency_tracking_enabled() -> bool:
        value = EnvHelper.get_env_variable_value_by_name("LATENCY_TRACKING_ENABLED", fails_if_missing=False)
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_latency_logging_enabled() -> bool:
        value = EnvHelper.get_env_variable_value_by_name("LATENCY_LOGGING_ENABLED", fails_if_missing=False)
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_latency_file_logging_enabled() -> bool:
        value = EnvHelper.get_env_variable_value_by_name("LATENCY_FILE_LOGGING_ENABLED", fails_if_missing=False)
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_latency_metrics_file_path() -> str:
        return EnvHelper.get_env_variable_value_by_name("LATENCY_METRICS_FILE_PATH", fails_if_missing=False) or "outputs/logs/latency_metrics.jsonl"

    # Google Calendar configuration methods
    @staticmethod
    def get_calendar_provider() -> str:
        """Get the calendar provider to use (salesforce or google)"""
        return EnvHelper.get_env_variable_value_by_name("CALENDAR_PROVIDER", fails_if_missing=False) or "salesforce"

    @staticmethod
    def get_google_calendar_credentials_filepath() -> str:
        """Get the path to Google Calendar service account credentials JSON file"""
        return EnvHelper.get_env_variable_value_by_name("GOOGLE_CALENDAR_CREDENTIALS_FILEPATH", fails_if_missing=False) or "secrets/google-calendar-service-account.json"

    @staticmethod
    def get_google_calendar_id() -> str:
        """Get the Google Calendar ID to use for appointments"""
        return EnvHelper.get_env_variable_value_by_name("GOOGLE_CALENDAR_ID", fails_if_missing=False) or "primary"

    @staticmethod
    def get_google_calendar_timezone() -> str:
        """Get the timezone for Google Calendar operations"""
        return EnvHelper.get_env_variable_value_by_name("GOOGLE_CALENDAR_TIMEZONE", fails_if_missing=False) or "Europe/Paris"

    # Business hours configuration methods
    @staticmethod
    def get_business_hours_slots() -> str:
        """
        Get business hours time slots in format "09:00-12:00,13:00-16:00".

        Returns:
            str: Comma-separated time slots in HH:MM-HH:MM format
        """
        return EnvHelper.get_env_variable_value_by_name("BUSINESS_HOURS_SLOTS", fails_if_missing=False) or ""

    @staticmethod
    def get_business_weekdays() -> str:
        """
        Get allowed business weekdays in format "0,1,2,3,4" (Monday=0, Sunday=6).

        Returns:
            str: Comma-separated weekday numbers
        """
        return EnvHelper.get_env_variable_value_by_name("BUSINESS_WEEKDAYS", fails_if_missing=False) or ""

    @staticmethod
    def get_business_timezone() -> str:
        """
        Get the timezone for business hours operations.

        Returns:
            str: Timezone string (e.g., "Europe/Paris")
        """
        return EnvHelper.get_env_variable_value_by_name("BUSINESS_TIMEZONE", fails_if_missing=False) or "Europe/Paris"

    @staticmethod
    def get_business_max_days_ahead() -> int:
        """
        Get the maximum number of days ahead appointments can be scheduled.

        Returns:
            int: Maximum days ahead (default: 30)
        """
        value = EnvHelper.get_env_variable_value_by_name("BUSINESS_MAX_DAYS_AHEAD", fails_if_missing=False)
        return int(value) if value else 30

    @staticmethod
    def get_business_appointment_duration() -> int:
        """
        Get the default appointment duration in minutes.

        Returns:
            int: Appointment duration in minutes (default: 30)
        """
        value = EnvHelper.get_env_variable_value_by_name("BUSINESS_APPOINTMENT_DURATION", fails_if_missing=False)
        return int(value) if value else 30

    @staticmethod
    def get_sms_appointment_confirmation_enabled() -> bool:
        """
        Get whether to send SMS confirmation when an appointment is created.

        Returns:
            bool: True if SMS confirmation should be sent, False otherwise (default: False)
        """
        value = EnvHelper.get_env_variable_value_by_name("SMS_APPOINTMENT_CONFIRMATION", fails_if_missing=False)
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_ga4_tracking_enabled() -> bool:
        """
        Get whether Google Analytics 4 tracking is enabled.

        Returns:
            bool: True if GA4 tracking is enabled, False otherwise (default: False)
        """
        value = EnvHelper.get_env_variable_value_by_name("GA4_TRACKING_ENABLED", fails_if_missing=False)
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_ga4_measurement_id() -> str:
        """
        Get the Google Analytics 4 Measurement ID.

        Returns:
            str: The GA4 Measurement ID (e.g., G-XXXXXXXXXX)
        """
        return EnvHelper.get_env_variable_value_by_name("GA4_MEASUREMENT_ID", fails_if_missing=False) or ""

    @staticmethod
    def get_ga4_api_secret() -> str:
        """
        Get the Google Analytics 4 API Secret.

        Returns:
            str: The GA4 API Secret for Measurement Protocol
        """
        return EnvHelper.get_env_variable_value_by_name("GA4_API_SECRET", fails_if_missing=False) or ""
