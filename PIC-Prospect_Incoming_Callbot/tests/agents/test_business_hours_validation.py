"""
Comprehensive tests for business hours validation functionality.

This module tests the BusinessHoursConfig class and its integration
with the CalendarAgent for appointment time validation.
"""

import os
import sys
import tempfile
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
import pytz
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app"))

from agents.calendar_agent import CalendarAgent
from agents.text_registry import TextRegistry
from utils.business_hours_config import BusinessHoursConfig, ValidationResult


class TestBusinessHoursConfig:
    """Test cases for BusinessHoursConfig class"""

    def setup_method(self):
        """Set up test fixtures before each test method"""
        # Set a consistent time for all tests:  7:00 AM french timezone
        self.fixed_now = pytz.timezone("Europe/Paris").localize(datetime(2025, 1, 20, 7, 0, 0))

    def test_default_configuration(self):
        """Test that default configuration is loaded correctly"""
        config = BusinessHoursConfig()

        # Test default values
        assert config.time_slots == [("09:00", "12:00"), ("13:00", "16:00")]
        assert config.allowed_weekdays == [0, 1, 2, 3, 4]  # Monday to Friday
        assert config.max_days_ahead == 30
        assert config.appointment_duration == 30
        assert config.timezone.zone == "Europe/Paris"

    def test_yaml_configuration_loading(self):
        """Test loading configuration from YAML file"""
        # Create temporary YAML configuration
        yaml_content = {
            "appointments": {
                "duration_minutes": 45,
                "working_hours": {"time_slots": [["08:00", "12:00"], ["14:00", "18:00"]]},
                "allowed_weekdays": [0, 1, 2, 3, 4, 5],  # Monday to Saturday
                "max_days_ahead": 60,
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            temp_yaml_path = f.name

        try:
            config = BusinessHoursConfig(temp_yaml_path)

            assert config.time_slots == [("08:00", "12:00"), ("14:00", "18:00")]
            assert config.allowed_weekdays == [0, 1, 2, 3, 4, 5]
            assert config.max_days_ahead == 60
            assert config.appointment_duration == 45
        finally:
            os.unlink(temp_yaml_path)

    def test_environment_variable_override(self):
        """Test that environment variables override YAML configuration"""
        with patch.dict(
            os.environ,
            {
                "BUSINESS_HOURS_SLOTS": "10:00-11:00,15:00-17:00",
                "BUSINESS_WEEKDAYS": "1,2,3",  # Tuesday to Thursday
                "BUSINESS_TIMEZONE": "US/Eastern",
            },
        ):
            config = BusinessHoursConfig()

            assert config.time_slots == [("10:00", "11:00"), ("15:00", "17:00")]
            assert config.allowed_weekdays == [1, 2, 3]
            assert config.timezone.zone == "US/Eastern"

    def test_legacy_yaml_format_support(self):
        """Test backward compatibility with legacy YAML format"""
        yaml_content = {"appointments": {"working_hours": {"start": "08:00", "end": "17:00"}}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            temp_yaml_path = f.name

        try:
            config = BusinessHoursConfig(temp_yaml_path)

            # Legacy format should be converted to two slots
            assert config.time_slots == [("08:00", "12:00"), ("13:00", "17:00")]
        finally:
            os.unlink(temp_yaml_path)

    def test_valid_appointment_monday_morning(self):
        """Test valid appointment on Monday morning"""
        config = BusinessHoursConfig()
        test_datetime = pytz.timezone("Europe/Paris").localize(datetime(2025, 1, 20, 10, 0))

        with patch("utils.business_hours_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = self.fixed_now
            result = config.validate_appointment_time(test_datetime, self.fixed_now)
            assert result == ValidationResult.VALID

    def test_valid_appointment_tuesday_afternoon(self):
        """Test valid appointment on Tuesday afternoon"""
        config = BusinessHoursConfig()
        test_datetime = pytz.timezone("Europe/Paris").localize(datetime(2025, 1, 21, 14, 30))

        with patch("utils.business_hours_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = self.fixed_now
            result = config.validate_appointment_time(test_datetime, self.fixed_now)
            assert result == ValidationResult.VALID

    def test_valid_appointment_friday_morning(self):
        """Test valid appointment on Friday morning"""
        config = BusinessHoursConfig()
        test_datetime = pytz.timezone("Europe/Paris").localize(datetime(2025, 1, 24, 9, 0))

        with patch("utils.business_hours_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = self.fixed_now
            result = config.validate_appointment_time(test_datetime, self.fixed_now)
            assert result == ValidationResult.VALID

    def test_appointment_before_opening_hours(self):
        """Test appointment before opening hours"""
        config = BusinessHoursConfig()
        test_datetime = pytz.timezone("Europe/Paris").localize(datetime(2025, 1, 20, 8, 0))

        with patch("utils.business_hours_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = self.fixed_now
            result = config.validate_appointment_time(test_datetime, self.fixed_now)
            assert result == ValidationResult.OUTSIDE_HOURS

    def test_appointment_after_closing_hours(self):
        """Test appointment after closing hours"""
        config = BusinessHoursConfig()
        test_datetime = pytz.timezone("Europe/Paris").localize(datetime(2025, 1, 20, 17, 0))

        with patch("utils.business_hours_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = self.fixed_now
            result = config.validate_appointment_time(test_datetime, self.fixed_now)
            assert result == ValidationResult.OUTSIDE_HOURS

    def test_appointment_during_lunch_break(self):
        """Test appointment during lunch break"""
        config = BusinessHoursConfig()
        test_datetime = pytz.timezone("Europe/Paris").localize(datetime(2025, 1, 20, 12, 30))

        with patch("utils.business_hours_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = self.fixed_now
            result = config.validate_appointment_time(test_datetime, self.fixed_now)
            assert result == ValidationResult.OUTSIDE_HOURS

    def test_appointment_on_saturday(self):
        """Test appointment on Saturday (weekend)"""
        config = BusinessHoursConfig()
        test_datetime = pytz.timezone("Europe/Paris").localize(datetime(2025, 1, 25, 10, 0))

        with patch("utils.business_hours_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = self.fixed_now
            result = config.validate_appointment_time(test_datetime, self.fixed_now)
            assert result == ValidationResult.WEEKEND

    def test_appointment_on_sunday(self):
        """Test appointment on Sunday (weekend)"""
        config = BusinessHoursConfig()
        test_datetime = pytz.timezone("Europe/Paris").localize(datetime(2025, 1, 26, 14, 0))

        with patch("utils.business_hours_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = self.fixed_now
            result = config.validate_appointment_time(test_datetime, self.fixed_now)
            assert result == ValidationResult.WEEKEND

    def test_appointment_in_past(self):
        """Test appointment in the past"""
        config = BusinessHoursConfig()
        test_datetime = pytz.timezone("Europe/Paris").localize(datetime(2024, 12, 1, 10, 0))

        with patch("utils.business_hours_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = self.fixed_now
            result = config.validate_appointment_time(test_datetime, self.fixed_now)
            assert result == ValidationResult.IN_PAST

    def test_appointment_too_far_future_default_limit(self):
        """Test appointment beyond the default 30-day limit"""
        config = BusinessHoursConfig()

        with patch("utils.business_hours_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = self.fixed_now

            # Appointment 31 days in future (beyond default 30-day limit)
            far_future = datetime(2025, 2, 20, 10, 0, tzinfo=pytz.timezone("Europe/Paris"))
            result = config.validate_appointment_time(far_future, self.fixed_now)
            assert result == ValidationResult.TOO_FAR_FUTURE

    def test_appointment_too_far_future_custom_limit(self):
        """Test appointment beyond a custom day limit"""
        config = BusinessHoursConfig()
        config.max_days_ahead = 14  # Custom 14-day limit

        with patch("utils.business_hours_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = self.fixed_now

            # Appointment 15 days in future (beyond 14-day limit)
            far_future = datetime(2025, 2, 4, 10, 0, tzinfo=pytz.timezone("Europe/Paris"))
            result = config.validate_appointment_time(far_future, self.fixed_now)
            assert result == ValidationResult.TOO_FAR_FUTURE

    def test_appointment_exactly_at_limit(self):
        """Test appointment exactly at the day limit (should be valid)"""
        config = BusinessHoursConfig()
        config.max_days_ahead = 14

        with patch("utils.business_hours_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = self.fixed_now

            # Appointment exactly 14 days in future (at the limit)
            at_limit = datetime(2025, 2, 3, 10, 0, tzinfo=pytz.timezone("Europe/Paris"))
            result = config.validate_appointment_time(at_limit, self.fixed_now)
            assert result == ValidationResult.VALID

    def test_appointment_very_far_future(self):
        """Test appointment very far in the future (several months)"""
        config = BusinessHoursConfig()

        with patch("utils.business_hours_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = self.fixed_now

            # Appointment 6 months in future
            very_far_future = datetime(2025, 7, 20, 10, 0, tzinfo=pytz.timezone("Europe/Paris"))
            result = config.validate_appointment_time(very_far_future, self.fixed_now)
            assert result == ValidationResult.TOO_FAR_FUTURE

    def test_appointment_one_minute_in_past(self):
        """Test appointment just one minute in the past"""
        config = BusinessHoursConfig()
        # Use a specific time for this edge case test
        now = datetime(2025, 1, 20, 10, 30, tzinfo=pytz.timezone("Europe/Paris"))

        with patch("utils.business_hours_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = now

            # Appointment 1 minute ago
            past_time = datetime(2025, 1, 20, 10, 29, tzinfo=pytz.timezone("Europe/Paris"))
            result = config.validate_appointment_time(past_time, now)
            assert result == ValidationResult.IN_PAST

    def test_appointment_same_time_as_now(self):
        """Test appointment at exactly the current time"""
        config = BusinessHoursConfig()
        # Use a specific time for this edge case test
        now = datetime(2025, 1, 20, 10, 30, tzinfo=pytz.timezone("Europe/Paris"))

        with patch("utils.business_hours_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = now

            # Appointment at the exact same time
            same_time = datetime(2025, 1, 20, 10, 30, tzinfo=pytz.timezone("Europe/Paris"))
            result = config.validate_appointment_time(same_time, now)
            assert result == ValidationResult.IN_PAST

    def test_appointment_yesterday_same_time(self):
        """Test appointment yesterday at the same time"""
        config = BusinessHoursConfig()

        with patch("utils.business_hours_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = self.fixed_now

            # Appointment yesterday
            yesterday = datetime(2025, 1, 19, 10, 30, tzinfo=pytz.timezone("Europe/Paris"))
            result = config.validate_appointment_time(yesterday, self.fixed_now)
            assert result == ValidationResult.IN_PAST

    def test_appointment_last_week(self):
        """Test appointment last week"""
        config = BusinessHoursConfig()

        with patch("utils.business_hours_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = self.fixed_now

            # Appointment last week
            last_week = datetime(2025, 1, 13, 10, 30, tzinfo=pytz.timezone("Europe/Paris"))
            result = config.validate_appointment_time(last_week, self.fixed_now)
            assert result == ValidationResult.IN_PAST

    def test_appointment_early_morning_edge_case(self):
        """Test appointment very early in the morning (edge of business hours)"""
        config = BusinessHoursConfig()

        with patch("utils.business_hours_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = self.fixed_now

            # Appointment at exactly 9:00 AM (start of business hours)
            start_time = datetime(2025, 1, 20, 9, 0, tzinfo=pytz.timezone("Europe/Paris"))
            result = config.validate_appointment_time(start_time, self.fixed_now)
            assert result == ValidationResult.VALID

    def test_appointment_late_afternoon_edge_case(self):
        """Test appointment at the end of business hours"""
        config = BusinessHoursConfig()

        with patch("utils.business_hours_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = self.fixed_now

            # Appointment at exactly 3:30 PM (end of afternoon slot)
            end_time = datetime(2025, 1, 20, 15, 30, tzinfo=pytz.timezone("Europe/Paris"))
            result = config.validate_appointment_time(end_time, self.fixed_now)
            assert result == ValidationResult.VALID

    def test_appointment_just_after_lunch_break(self):
        """Test appointment right after lunch break starts"""
        config = BusinessHoursConfig()

        with patch("utils.business_hours_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = self.fixed_now

            # Appointment at exactly 1:00 PM (start of afternoon slot)
            after_lunch = datetime(2025, 1, 20, 13, 0, tzinfo=pytz.timezone("Europe/Paris"))
            result = config.validate_appointment_time(after_lunch, self.fixed_now)
            assert result == ValidationResult.VALID

    def test_business_hours_display_french(self):
        """Test French display format for business hours"""
        config = BusinessHoursConfig()
        display = config.get_business_hours_display()

        # Should show weekdays and time slots in French
        assert "du lundi au vendredi" in display
        assert "de 9h à 12h" in display
        assert "de 13h à 16h" in display

    def test_custom_weekdays_display(self):
        """Test display for custom weekday configuration"""
        config = BusinessHoursConfig()
        config.allowed_weekdays = [0, 2, 4]  # Monday, Wednesday, Friday

        display = config.get_business_hours_display()
        assert "lundi, mercredi, vendredi" in display

    def test_business_day_checking(self):
        """Test business day validation"""
        config = BusinessHoursConfig()

        # Test regular business days
        monday = datetime(2025, 1, 20).date()  # Monday
        friday = datetime(2025, 1, 24).date()  # Friday
        saturday = datetime(2025, 1, 25).date()  # Saturday

        assert config.is_business_day(monday) is True
        assert config.is_business_day(friday) is True
        assert config.is_business_day(saturday) is False

    def test_next_business_day(self):
        """Test finding next business day"""
        config = BusinessHoursConfig()

        # From Thursday, next business day should be Friday
        thursday = datetime(2025, 1, 23).date()  # Thursday
        friday = datetime(2025, 1, 24).date()  # Friday

        next_day = config.get_next_business_day(thursday)
        assert next_day == friday

        # From Friday, next business day should be Monday
        friday = datetime(2025, 1, 24).date()  # Friday
        monday = datetime(2025, 1, 27).date()  # Monday

        next_day = config.get_next_business_day(friday)
        assert next_day == monday

    def test_available_timeframe_params(self):
        """Test parameters for timeframe calculation"""
        config = BusinessHoursConfig()
        params = config.get_available_timeframe_params()

        assert "availability_timeframe" in params
        assert "max_weekday" in params
        assert "slot_duration_minutes" in params
        assert params["availability_timeframe"] == config.time_slots
        assert params["slot_duration_minutes"] == config.appointment_duration


class TestCalendarAgentBusinessHoursIntegration:
    """Test integration of business hours validation with CalendarAgent"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_salesforce_client = Mock()
        self.mock_llm = Mock()

        # Set a consistent time for all tests
        test_time = datetime(2025, 1, 15, 7, 0, 0)  # Monday 7:00 AM
        CalendarAgent.now = pytz.timezone("Europe/Paris").localize(test_time)

        # Create calendar agent
        self.agent = CalendarAgent(self.mock_salesforce_client, self.mock_llm, self.mock_llm, self.mock_llm)

    def test_validate_appointment_time_method(self):
        """Test the validate_appointment_time_async method"""
        with patch("utils.business_hours_config.datetime") as mock_datetime:
            # Mock current time to be earlier than test times
            now = datetime(2025, 1, 15, 7, 0, tzinfo=pytz.timezone("Europe/Paris"))
            mock_datetime.now.return_value = now
            CalendarAgent.now = now

            # Test valid appointment
            valid_time = datetime(2025, 1, 20, 10, 0, tzinfo=pytz.timezone("Europe/Paris"))
            result = self.agent.validate_appointment_time_async(valid_time)
            assert result == "valid"

            # Test weekend appointment
            weekend_time = datetime(2025, 1, 25, 10, 0, tzinfo=pytz.timezone("Europe/Paris"))
            result = self.agent.validate_appointment_time_async(weekend_time)
            assert result == "weekend"

            # Test outside hours
            early_time = datetime(2025, 1, 20, 8, 0, tzinfo=pytz.timezone("Europe/Paris"))
            result = self.agent.validate_appointment_time_async(early_time)
            assert result.startswith("outside_hours:")

    @pytest.mark.asyncio
    async def test_business_hours_validation_in_run_async(self):
        """Test business hours validation integration in run_async"""
        with patch("utils.business_hours_config.datetime") as mock_datetime:
            # Mock current time to be earlier than test times
            now = datetime(2025, 1, 15, 7, 0, tzinfo=pytz.timezone("Europe/Paris"))
            mock_datetime.now.return_value = now
            CalendarAgent.now = now

            # Mock the date extraction to return a weekend appointment
            weekend_appointment = datetime(2025, 1, 25, 10, 0, tzinfo=pytz.timezone("Europe/Paris"))

            with patch.object(self.agent, "_extract_appointment_selected_date_and_time_async") as mock_extract:
                with patch.object(self.agent, "categorize_request_for_dispatch_async") as mock_categorize:
                    mock_extract.return_value = weekend_appointment
                    mock_categorize.return_value = "Demande de confirmation du rendez-vous"

                    result = await self.agent.schedule_new_appointement_async("Je veux un rendez-vous samedi", [])

                    # Should return weekend error message
                    assert result == TextRegistry.appointment_weekend_text

    @pytest.mark.asyncio
    async def test_outside_hours_validation_message(self):
        """Test outside hours validation returns correct message with business hours"""
        with patch("utils.business_hours_config.datetime") as mock_datetime:
            # Mock current time to be earlier than test times
            now = datetime(2025, 1, 15, 7, 0, tzinfo=pytz.timezone("Europe/Paris"))
            mock_datetime.now.return_value = now
            CalendarAgent.now = now

            # Mock appointment outside business hours
            outside_hours_appointment = datetime(2025, 1, 20, 8, 0, tzinfo=pytz.timezone("Europe/Paris"))

            with patch.object(self.agent, "_extract_appointment_selected_date_and_time_async") as mock_extract:
                with patch.object(self.agent, "categorize_request_for_dispatch_async") as mock_categorize:
                    mock_extract.return_value = outside_hours_appointment
                    mock_categorize.return_value = "Demande de confirmation du rendez-vous"

                    result = await self.agent.schedule_new_appointement_async("Je veux un rendez-vous à 8h", [])

                    # Should return outside hours error with business hours info
                    assert "les rendez-vous ne peuvent être pris qu'aux heures ouvrées" in result
                    assert "du lundi au vendredi" in result

    def test_business_hours_config_class_level_access(self):
        """Test that business hours config is accessible at class level"""
        assert CalendarAgent.business_hours_config is not None
        assert isinstance(CalendarAgent.business_hours_config, BusinessHoursConfig)

    def test_get_available_timeframes_uses_business_config(self):
        """Test that get_available_timeframes_from_scheduled_slots uses business config"""
        # Create test data
        start_date = "2025-01-20T00:00:00Z"
        end_date = "2025-01-24T23:59:59Z"
        scheduled_slots = []

        # Call with business hours config
        result = CalendarAgent.get_available_timeframes_from_scheduled_slots(start_date, end_date, scheduled_slots, business_hours_config=self.agent.business_hours_config)

        # Should return available timeframes based on business config
        assert isinstance(result, list)
        # The exact results depend on the current date, but it should not be empty
        # for a weekday range with default business hours


class TestBusinessHoursErrorMessages:
    """Test that error messages are properly formatted and localized"""

    def test_all_error_texts_exist(self):
        """Test that all required error texts exist in TextRegistry"""
        required_texts = ["appointment_outside_hours_text", "appointment_weekend_text", "appointment_in_past_text", "appointment_holiday_text"]

        for text_name in required_texts:
            assert hasattr(TextRegistry, text_name)
            text_value = getattr(TextRegistry, text_name)
            assert isinstance(text_value, str)
            assert len(text_value) > 0

    def test_outside_hours_text_formatting(self):
        """Test that outside hours text supports business hours formatting"""
        text = TextRegistry.appointment_outside_hours_text
        assert "{business_hours}" in text

        # Test formatting with sample business hours
        sample_hours = "du lundi au vendredi, de 9h à 12h et de 13h à 16h"
        formatted = text.format(business_hours=sample_hours)
        assert sample_hours in formatted
        assert "{business_hours}" not in formatted


class TestBusinessHoursEdgeCases:
    """Test edge cases and error handling"""

    def test_invalid_yaml_file_handling(self):
        """Test handling of invalid YAML configuration"""
        # Create invalid YAML file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [")
            temp_yaml_path = f.name

        try:
            # Should not raise exception, should fall back to defaults
            config = BusinessHoursConfig(temp_yaml_path)
            assert config.time_slots == [("09:00", "12:00"), ("13:00", "16:00")]
        finally:
            os.unlink(temp_yaml_path)

    def test_missing_config_file(self):
        """Test behavior with missing configuration file"""
        # Should not raise exception, should use defaults
        config = BusinessHoursConfig("nonexistent_file.yaml")
        assert config.time_slots == [("09:00", "12:00"), ("13:00", "16:00")]

    def test_invalid_environment_variables(self):
        """Test handling of invalid environment variable values"""
        with patch.dict(os.environ, {"BUSINESS_HOURS_SLOTS": "invalid_format_no_dash", "BUSINESS_WEEKDAYS": "not-numbers", "BUSINESS_TIMEZONE": "Invalid/Timezone"}):
            # Should not raise exception, should fall back to defaults
            config = BusinessHoursConfig()
            assert config.time_slots == [("09:00", "12:00"), ("13:00", "16:00")]
            assert config.allowed_weekdays == [0, 1, 2, 3, 4]
            assert config.timezone.zone == "Europe/Paris"

    def test_none_datetime_validation(self):
        """Test validation with None datetime"""
        now = datetime(2025, 1, 20, 8, 0, tzinfo=pytz.timezone("Europe/Paris"))
        config = BusinessHoursConfig()
        result = config.validate_appointment_time(None, now)
        assert result == ValidationResult.OUTSIDE_HOURS

    def test_timezone_conversion(self):
        """Test timezone conversion in validation"""
        config = BusinessHoursConfig()

        # Test with datetime in different timezone
        us_eastern = pytz.timezone("US/Eastern")
        us_time = us_eastern.localize(datetime(2025, 1, 20, 4, 0))  # 4 AM EST = 10 AM Paris

        with patch("utils.business_hours_config.datetime") as mock_datetime:
            now = datetime(2025, 1, 20, 8, 0, tzinfo=pytz.timezone("Europe/Paris"))
            mock_datetime.now.return_value = now

            result = config.validate_appointment_time(us_time, now)
            assert result == ValidationResult.VALID  # Should be valid when converted to Paris time
