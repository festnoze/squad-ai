"""
Business Hours Configuration for Calendar Agent

This module provides centralized configuration and validation for business hours,
including allowed days, time slots, and timezone handling.
"""

import logging
from datetime import datetime, time
from enum import Enum
from typing import List, Tuple
import pytz
import yaml
import os


class ValidationResult(Enum):
    """Enum for business hours validation results"""
    VALID = "valid"
    OUTSIDE_HOURS = "outside_hours"
    WEEKEND = "weekend"
    HOLIDAY = "holiday"
    TOO_FAR_FUTURE = "too_far_future"
    IN_PAST = "in_past"


class BusinessHoursConfig:
    """
    Centralized configuration for business hours and appointment validation.

    Supports multiple time slots per day, configurable weekdays, timezone handling,
    and various validation rules for appointment scheduling.
    """

    def __init__(self, config_file_path: str = "app/agents/configs/calendar_agent.yaml"):
        """
        Initialize business hours configuration.

        Args:
            config_file_path: Path to the YAML configuration file
        """
        self.logger = logging.getLogger(__name__)
        self.config_file_path = config_file_path
        self.timezone = pytz.timezone("Europe/Paris")

        # Default values
        self._default_time_slots = [("09:00", "12:00"), ("13:00", "16:00")]
        self._default_allowed_weekdays = [0, 1, 2, 3, 4]  # Monday to Friday
        self._default_max_days_ahead = 30
        self._default_appointment_duration = 30

        # Load configuration
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from YAML file and environment variables."""
        # Load from YAML file if it exists
        config_data = {}
        if os.path.exists(self.config_file_path):
            try:
                with open(self.config_file_path, 'r', encoding='utf-8') as file:
                    config_data = yaml.safe_load(file) or {}
            except Exception as e:
                self.logger.warning(f"Could not load config file {self.config_file_path}: {e}")

        # Extract appointments section
        appointments_config = config_data.get('appointments', {})
        working_hours_config = appointments_config.get('working_hours', {})

        # Load allowed weekdays first
        self.allowed_weekdays = self._parse_allowed_weekdays(appointments_config)

        # Load time slots
        self.time_slots = self._parse_time_slots(working_hours_config)

        # Load other settings
        self.max_days_ahead = appointments_config.get('max_days_ahead', appointments_config.get('days_ahead', self._default_max_days_ahead))

        # Load appointment duration - environment variable takes precedence
        env_duration = self._get_env_or_default('BUSINESS_APPOINTMENT_DURATION', None)
        if env_duration:
            try:
                self.appointment_duration = int(env_duration)
            except ValueError:
                self.logger.warning(f"Invalid BUSINESS_APPOINTMENT_DURATION '{env_duration}', using config/default")
                self.appointment_duration = appointments_config.get('duration_minutes', self._default_appointment_duration)
        else:
            self.appointment_duration = appointments_config.get('duration_minutes', self._default_appointment_duration)

        # Load timezone
        timezone_str = self._get_env_or_default('BUSINESS_TIMEZONE', 'Europe/Paris')
        try:
            self.timezone = pytz.timezone(timezone_str)
        except Exception as e:
            self.logger.warning(f"Invalid timezone {timezone_str}: {e}. Using Europe/Paris")
            self.timezone = pytz.timezone("Europe/Paris")

    def _parse_time_slots(self, working_hours_config: dict) -> List[Tuple[str, str]]:
        """Parse time slots from configuration."""
        # Try environment variable first
        env_slots = self._get_env_or_default('BUSINESS_HOURS_SLOTS', None)
        if env_slots:
            try:
                # Parse format like "09:00-12:00,13:00-16:00"
                slots = []
                for slot_str in env_slots.split(','):
                    if '-' in slot_str:
                        start_time, end_time = slot_str.strip().split('-', 1)
                        slots.append((start_time.strip(), end_time.strip()))
                if slots:  # Only return if we successfully parsed some slots
                    return slots
            except Exception as e:
                self.logger.warning(f"Could not parse BUSINESS_HOURS_SLOTS '{env_slots}': {e}")

        # Try new YAML time_slots format
        if 'time_slots' in working_hours_config:
            try:
                time_slots = working_hours_config['time_slots']
                if isinstance(time_slots, list):
                    slots = []
                    for slot in time_slots:
                        if isinstance(slot, list) and len(slot) == 2:
                            slots.append((slot[0], slot[1]))
                    if slots:
                        return slots
            except Exception as e:
                self.logger.warning(f"Could not parse time_slots from YAML: {e}")

        # Try legacy YAML config (single start/end)
        if 'start' in working_hours_config and 'end' in working_hours_config:
            start_time = working_hours_config['start']
            end_time = working_hours_config['end']
            # Convert single time range to two slots (morning and afternoon)
            return [(start_time, "12:00"), ("13:00", end_time)]

        # Use default
        return self._default_time_slots

    def _parse_allowed_weekdays(self, appointments_config: dict) -> List[int]:
        """Parse allowed weekdays from configuration."""
        # Try environment variable first
        env_weekdays = self._get_env_or_default('BUSINESS_WEEKDAYS', None)
        if env_weekdays:
            try:
                # Parse format like "0,1,2,3,4" (Monday=0, Sunday=6)
                return [int(day.strip()) for day in env_weekdays.split(',') if day.strip()]
            except Exception as e:
                self.logger.warning(f"Could not parse BUSINESS_WEEKDAYS '{env_weekdays}': {e}")

        # Try YAML config
        if 'allowed_weekdays' in appointments_config:
            weekdays = appointments_config['allowed_weekdays']
            if isinstance(weekdays, list):
                return weekdays

        # Use default (Monday to Friday)
        return self._default_allowed_weekdays

    def _get_env_or_default(self, env_var: str, default_value: str | None = None) -> str:
        """Get environment variable value or return default."""
        return os.getenv(env_var, default_value)

    def validate_appointment_time(self, requested_datetime: datetime | None, now: datetime) -> ValidationResult:
        """
        Validate if the requested appointment time is within business hours.

        Args:
            requested_datetime: The datetime for the requested appointment

        Returns:
            ValidationResult indicating if the time is valid or why it's invalid
        """
        
        if not requested_datetime:
            return ValidationResult.OUTSIDE_HOURS

        # Ensure datetime has timezone info
        if requested_datetime.tzinfo is None:
            requested_datetime = self.timezone.localize(requested_datetime)
        else:
            # Convert to business timezone
            requested_datetime = requested_datetime.astimezone(self.timezone)

        # Check if appointment is in the past
        if requested_datetime <= now:
            return ValidationResult.IN_PAST

        # Check if appointment is too far in the future
        days_ahead = (requested_datetime.date() - now.date()).days
        if days_ahead > self.max_days_ahead:
            return ValidationResult.TOO_FAR_FUTURE

        # Check if it's an allowed weekday
        if requested_datetime.weekday() not in self.allowed_weekdays:
            return ValidationResult.WEEKEND

        # Check if time is within business hours
        requested_time = requested_datetime.time()
        for start_time_str, end_time_str in self.time_slots:
            start_time = time.fromisoformat(start_time_str)
            end_time = time.fromisoformat(end_time_str)

            if start_time <= requested_time < end_time:
                return ValidationResult.VALID

        return ValidationResult.OUTSIDE_HOURS

    def get_business_hours_display(self) -> str:
        """
        Get a human-readable description of business hours in French.

        Returns:
            String describing the business hours and days
        """
        # Format weekdays
        french_days = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
        allowed_day_names = [french_days[day] for day in sorted(self.allowed_weekdays)]

        if len(allowed_day_names) == 5 and allowed_day_names == ["lundi", "mardi", "mercredi", "jeudi", "vendredi"]:
            days_str = "du lundi au vendredi"
        else:
            days_str = ", ".join(allowed_day_names)

        # Format time slots
        time_slots_str = []
        for start_time, end_time in self.time_slots:
            start_hour = int(start_time.split(':')[0])
            end_hour = int(end_time.split(':')[0])
            start_minute = start_time.split(':')[1]
            end_minute = end_time.split(':')[1]

            start_str = f"{start_hour}h{start_minute if start_minute != '00' else ''}"
            end_str = f"{end_hour}h{end_minute if end_minute != '00' else ''}"
            time_slots_str.append(f"de {start_str} à {end_str}")

        if len(time_slots_str) == 1:
            hours_str = time_slots_str[0]
        else:
            hours_str = " et ".join(time_slots_str)

        return f"{days_str}, {hours_str}"

    def get_available_timeframe_params(self) -> dict:
        """
        Get parameters for the get_available_timeframes_from_scheduled_slots method.

        Returns:
            Dictionary with parameters for timeframe calculation
        """
        return {
            'availability_timeframe': self.time_slots,
            'max_weekday': max(self.allowed_weekdays) + 1 if self.allowed_weekdays else 5,
            'slot_duration_minutes': self.appointment_duration
        }

    def is_business_day(self, date: datetime.date) -> bool:
        """
        Check if a given date is a business day.

        Args:
            date: The date to check

        Returns:
            True if it's a business day, False otherwise
        """
        return date.weekday() in self.allowed_weekdays

    def get_next_business_day(self, from_date: datetime.date = None) -> datetime.date:
        """
        Get the next business day from a given date.

        Args:
            from_date: Starting date (defaults to today)

        Returns:
            The next business day
        """
        if from_date is None:
            from_date = datetime.now(self.timezone).date()

        # Start from the next day
        from datetime import timedelta
        next_date = from_date + timedelta(days=1)

        while not self.is_business_day(next_date):
            next_date += timedelta(days=1)

        return next_date