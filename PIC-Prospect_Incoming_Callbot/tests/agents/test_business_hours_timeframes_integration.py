"""
Integration tests for business hours configuration with get_available_timeframes_from_scheduled_slots.

This module tests that the business hours configuration properly integrates with
the timeframes calculation, ensuring weekday filtering and time slot validation work correctly.
"""

import pytest
import tempfile
import yaml
import os
from datetime import datetime
from unittest.mock import patch

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'app'))

from agents.calendar_agent import CalendarAgent
from utils.business_hours_config import BusinessHoursConfig


class TestBusinessHoursTimeframesIntegration:
    """Test integration between business hours config and timeframes calculation"""

    def test_weekday_filtering_with_business_config(self):
        """Test that business hours config properly filters weekdays"""
        # Create config with Tuesday-Thursday only
        config = BusinessHoursConfig()
        config.allowed_weekdays = [1, 2, 3]  # Tuesday, Wednesday, Thursday
        config.time_slots = [("09:00", "17:00")]

        # Test date range from Monday to Friday
        start_date = "2025-01-06T00:00:00Z"  # Monday
        end_date = "2025-01-10T23:59:59Z"    # Friday
        scheduled_slots = []

        result = CalendarAgent.get_available_timeframes_from_scheduled_slots(
            start_date, end_date, scheduled_slots,
            business_hours_config=config
        )

        # Should only include Tuesday (7th), Wednesday (8th), Thursday (9th)
        # Monday (6th) and Friday (10th) should be excluded
        expected_dates = ["2025-01-07", "2025-01-08", "2025-01-09"]

        for expected_date in expected_dates:
            assert any(expected_date in slot for slot in result), f"Missing slots for {expected_date}"

        # Should NOT include Monday or Friday
        excluded_dates = ["2025-01-06", "2025-01-10"]
        for excluded_date in excluded_dates:
            assert not any(excluded_date in slot for slot in result), f"Unexpectedly found slots for {excluded_date}"

    def test_time_slots_with_business_config(self):
        """Test that business hours config properly applies time slots"""
        # Create config with custom time slots
        config = BusinessHoursConfig()
        config.time_slots = [("08:00", "10:00"), ("14:00", "18:00")]
        config.appointment_duration = 60  # 1 hour slots

        start_date = "2025-01-06T00:00:00Z"  # Monday
        end_date = "2025-01-06T23:59:59Z"    # Monday
        scheduled_slots = []

        result = CalendarAgent.get_available_timeframes_from_scheduled_slots(
            start_date, end_date, scheduled_slots,
            business_hours_config=config
        )

        # Should have morning slot (8-9, adjusted for 1hr duration) and afternoon slot (14-17, adjusted)
        expected_slots = [
            "2025-01-06 08:00-09:00",  # 10:00 - 60min = 09:00
            "2025-01-06 14:00-17:00",  # 18:00 - 60min = 17:00
        ]

        assert sorted(result) == sorted(expected_slots)

    def test_weekend_exclusion_with_business_config(self):
        """Test that weekends are properly excluded when configured"""
        # Create config excluding weekends
        config = BusinessHoursConfig()
        config.allowed_weekdays = [0, 1, 2, 3, 4]  # Monday to Friday only
        config.time_slots = [("09:00", "17:00")]

        # Test weekend dates
        start_date = "2025-01-11T00:00:00Z"  # Saturday
        end_date = "2025-01-12T23:59:59Z"    # Sunday
        scheduled_slots = []

        result = CalendarAgent.get_available_timeframes_from_scheduled_slots(
            start_date, end_date, scheduled_slots,
            business_hours_config=config
        )

        # Should return no slots for weekend
        assert result == []

    def test_business_config_overrides_parameters(self):
        """Test that business config overrides method parameters"""
        # Create config with specific settings
        config = BusinessHoursConfig()
        config.time_slots = [("10:00", "12:00")]
        config.allowed_weekdays = [1, 3]  # Tuesday and Thursday only
        config.appointment_duration = 45

        start_date = "2025-01-06T00:00:00Z"  # Monday
        end_date = "2025-01-10T23:59:59Z"    # Friday
        scheduled_slots = []

        # Call with different parameters that should be overridden
        result = CalendarAgent.get_available_timeframes_from_scheduled_slots(
            start_date, end_date, scheduled_slots,
            slot_duration_minutes=30,  # Should be overridden to 45
            max_weekday=7,  # Should be overridden to exclude Monday, Wednesday, Friday
            availability_timeframe=[("08:00", "18:00")],  # Should be overridden
            business_hours_config=config
        )

        # Should only have slots for Tuesday and Thursday with 10-12 timeframe and 45min duration
        expected_slots = [
            "2025-01-07 10:00-11:15",  # Tuesday: 12:00 - 45min = 11:15
            "2025-01-09 10:00-11:15",  # Thursday: 12:00 - 45min = 11:15
        ]

        assert sorted(result) == sorted(expected_slots)

    def test_no_business_config_uses_defaults(self):
        """Test that method works with default parameters when no business config provided"""
        start_date = "2025-01-06T00:00:00Z"  # Monday
        end_date = "2025-01-06T23:59:59Z"    # Monday
        scheduled_slots = []

        result = CalendarAgent.get_available_timeframes_from_scheduled_slots(
            start_date, end_date, scheduled_slots
            # No business_hours_config parameter
        )

        # Should use default timeframes and settings
        expected_slots = [
            "2025-01-06 09:00-11:30",  # Default morning slot
            "2025-01-06 13:00-15:30",  # Default afternoon slot
        ]

        assert sorted(result) == sorted(expected_slots)

    def test_partial_business_config_override(self):
        """Test that business config only overrides specified values"""
        # Create config with only some values set
        config = BusinessHoursConfig()
        config.appointment_duration = 15  # Only override duration

        start_date = "2025-01-06T00:00:00Z"  # Monday
        end_date = "2025-01-06T23:59:59Z"    # Monday
        scheduled_slots = []

        result = CalendarAgent.get_available_timeframes_from_scheduled_slots(
            start_date, end_date, scheduled_slots,
            slot_duration_minutes=30,  # This should be overridden
            availability_timeframe=[("08:00", "10:00"), ("14:00", "16:00")],  # This should be used
            business_hours_config=config
        )

        # Should use custom timeframes but business config duration (15 min)
        expected_slots = [
            "2025-01-06 08:00-09:45",  # 10:00 - 15min = 09:45
            "2025-01-06 14:00-15:45",  # 16:00 - 15min = 15:45
        ]

        assert sorted(result) == sorted(expected_slots)

    @pytest.mark.parametrize("config_weekdays,expected_dates", [
        # Monday to Friday (default business days)
        ([0, 1, 2, 3, 4], ["2025-01-06", "2025-01-07", "2025-01-08", "2025-01-09", "2025-01-10"]),
        # Monday, Wednesday, Friday only
        ([0, 2, 4], ["2025-01-06", "2025-01-08", "2025-01-10"]),
        # Weekends only
        ([5, 6], []),  # No dates in our test range (Mon-Fri)
        # Tuesday and Thursday only
        ([1, 3], ["2025-01-07", "2025-01-09"]),
        # All days including weekend (if we extended range)
        ([0, 1, 2, 3, 4, 5, 6], ["2025-01-06", "2025-01-07", "2025-01-08", "2025-01-09", "2025-01-10"]),
    ])
    def test_various_weekday_configurations(self, config_weekdays, expected_dates):
        """Test different weekday configurations"""
        config = BusinessHoursConfig()
        config.allowed_weekdays = config_weekdays
        config.time_slots = [("09:00", "10:00")]

        start_date = "2025-01-06T00:00:00Z"  # Monday
        end_date = "2025-01-10T23:59:59Z"    # Friday
        scheduled_slots = []

        result = CalendarAgent.get_available_timeframes_from_scheduled_slots(
            start_date, end_date, scheduled_slots,
            business_hours_config=config
        )

        # Check that only expected dates appear in results
        for expected_date in expected_dates:
            assert any(expected_date in slot for slot in result), f"Missing slots for {expected_date}"

        # Check that no unexpected dates appear
        result_dates = set()
        for slot in result:
            date_part = slot.split(" ")[0]  # Extract "2025-01-06" from "2025-01-06 09:00-09:30"
            result_dates.add(date_part)

        assert result_dates == set(expected_dates)

    @pytest.mark.parametrize("time_slots,expected_time_ranges", [
        # Single morning slot
        ([("08:00", "12:00")], ["08:00-11:30"]),
        # Single afternoon slot
        ([("13:00", "17:00")], ["13:00-16:30"]),
        # Traditional business hours (morning + afternoon)
        ([("09:00", "12:00"), ("13:00", "17:00")], ["09:00-11:30", "13:00-16:30"]),
        # Extended day with lunch break
        ([("08:00", "12:00"), ("13:00", "18:00")], ["08:00-11:30", "13:00-17:30"]),
        # Three slots (morning, lunch, afternoon)
        ([("08:00", "10:00"), ("12:00", "14:00"), ("15:00", "18:00")], ["08:00-09:30", "12:00-13:30", "15:00-17:30"]),
        # Short slots
        ([("09:00", "09:30"), ("10:00", "10:30")], []),  # Too short after 30min adjustment
        # Minimal viable slots
        ([("09:00", "10:00"), ("11:00", "12:00")], ["09:00-09:30", "11:00-11:30"]),
    ])
    def test_various_time_slot_configurations(self, time_slots, expected_time_ranges):
        """Test different time slot configurations"""
        config = BusinessHoursConfig()
        config.time_slots = time_slots
        config.appointment_duration = 30  # 30 minute slots

        start_date = "2025-01-06T00:00:00Z"  # Monday
        end_date = "2025-01-06T23:59:59Z"    # Monday
        scheduled_slots = []

        result = CalendarAgent.get_available_timeframes_from_scheduled_slots(
            start_date, end_date, scheduled_slots,
            business_hours_config=config
        )

        # Extract time ranges from results (remove date part)
        result_time_ranges = []
        for slot in result:
            time_part = slot.split(" ")[1]  # Extract "09:00-11:30" from "2025-01-06 09:00-11:30"
            result_time_ranges.append(time_part)

        assert sorted(result_time_ranges) == sorted(expected_time_ranges)

    def test_yaml_config_integration_with_timeframes(self):
        """Test that YAML configuration properly integrates with timeframes calculation"""
        # Create temporary YAML configuration
        yaml_content = {
            'appointments': {
                'duration_minutes': 20,
                'working_hours': {
                    'time_slots': [["10:00", "12:00"], ["15:00", "17:00"]]
                },
                'allowed_weekdays': [1, 2, 3],  # Tuesday, Wednesday, Thursday
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(yaml_content, f)
            temp_yaml_path = f.name

        try:
            config = BusinessHoursConfig(temp_yaml_path)

            start_date = "2025-01-06T00:00:00Z"  # Monday
            end_date = "2025-01-10T23:59:59Z"    # Friday
            scheduled_slots = []

            result = CalendarAgent.get_available_timeframes_from_scheduled_slots(
                start_date, end_date, scheduled_slots,
                business_hours_config=config
            )

            # Should only include Tue, Wed, Thu with the specified time slots and 20min duration
            expected_slots = [
                "2025-01-07 10:00-11:40",  # Tuesday morning: 12:00 - 20min = 11:40
                "2025-01-07 15:00-16:40",  # Tuesday afternoon: 17:00 - 20min = 16:40
                "2025-01-08 10:00-11:40",  # Wednesday morning
                "2025-01-08 15:00-16:40",  # Wednesday afternoon
                "2025-01-09 10:00-11:40",  # Thursday morning
                "2025-01-09 15:00-16:40",  # Thursday afternoon
            ]

            assert sorted(result) == sorted(expected_slots)

        finally:
            os.unlink(temp_yaml_path)

    def test_environment_variable_integration_with_timeframes(self):
        """Test that environment variables properly integrate with timeframes calculation"""
        with patch.dict(os.environ, {
            'BUSINESS_HOURS_SLOTS': '11:00-13:00,16:00-18:00',
            'BUSINESS_WEEKDAYS': '0,4',  # Monday and Friday only
            'BUSINESS_APPOINTMENT_DURATION': '25'
        }):
            config = BusinessHoursConfig()

            start_date = "2025-01-06T00:00:00Z"  # Monday
            end_date = "2025-01-10T23:59:59Z"    # Friday
            scheduled_slots = []

            result = CalendarAgent.get_available_timeframes_from_scheduled_slots(
                start_date, end_date, scheduled_slots,
                business_hours_config=config
            )

            # Should only include Monday and Friday with env var time slots and 25min duration
            expected_slots = [
                "2025-01-06 11:00-12:35",  # Monday morning: 13:00 - 25min = 12:35
                "2025-01-06 16:00-17:35",  # Monday afternoon: 18:00 - 25min = 17:35
                "2025-01-10 11:00-12:35",  # Friday morning
                "2025-01-10 16:00-17:35",  # Friday afternoon
            ]

            assert sorted(result) == sorted(expected_slots)

    def test_complex_scenario_with_scheduled_appointments(self):
        """Test complex scenario with business config and existing appointments"""
        config = BusinessHoursConfig()
        config.time_slots = [("09:00", "12:00"), ("14:00", "18:00")]
        config.allowed_weekdays = [0, 1, 2]  # Monday, Tuesday, Wednesday
        config.appointment_duration = 30

        start_date = "2025-01-06T00:00:00Z"  # Monday
        end_date = "2025-01-08T23:59:59Z"    # Wednesday

        # Some appointments already scheduled
        scheduled_slots = [
            # Monday 10:00-11:00 taken
            {
                "StartDateTime": "2025-01-06T10:00:00Z",
                "EndDateTime": "2025-01-06T11:00:00Z"
            },
            # Tuesday 15:00-16:00 taken
            {
                "StartDateTime": "2025-01-07T15:00:00Z",
                "EndDateTime": "2025-01-07T16:00:00Z"
            }
        ]

        result = CalendarAgent.get_available_timeframes_from_scheduled_slots(
            start_date, end_date, scheduled_slots,
            business_hours_config=config
        )

        # Expected available slots with existing appointments taken into account
        expected_slots = [
            # Monday
            "2025-01-06 09:00-10:00",   # Before the 10-11 appointment
            "2025-01-06 11:00-11:30",   # After the 10-11 appointment (adjusted for 30min duration)
            "2025-01-06 14:00-17:30",   # Full afternoon slot (18:00 - 30min = 17:30)

            # Tuesday
            "2025-01-07 09:00-11:30",   # Full morning slot
            "2025-01-07 14:00-15:00",   # Before the 15-16 appointment
            "2025-01-07 16:00-17:30",   # After the 15-16 appointment

            # Wednesday
            "2025-01-08 09:00-11:30",   # Full morning slot
            "2025-01-08 14:00-17:30",   # Full afternoon slot
        ]

        assert sorted(result) == sorted(expected_slots)

    def test_business_config_with_no_valid_slots(self):
        """Test business config that results in no valid time slots"""
        config = BusinessHoursConfig()
        config.time_slots = [("09:00", "09:15")]  # Very short slot
        config.appointment_duration = 30  # Longer than the slot

        start_date = "2025-01-06T00:00:00Z"
        end_date = "2025-01-06T23:59:59Z"
        scheduled_slots = []

        result = CalendarAgent.get_available_timeframes_from_scheduled_slots(
            start_date, end_date, scheduled_slots,
            business_hours_config=config
        )

        # Should return no slots since 9:15 - 30min = invalid range
        assert result == []