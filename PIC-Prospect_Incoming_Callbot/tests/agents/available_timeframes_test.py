import pytest
from datetime import datetime, timedelta
from app.agents.calendar_agent import CalendarAgent
from unittest.mock import AsyncMock, patch

class DummyLLM:
    """Very small mock suitable for our unit tests."""
    def bind_tools(self, _tools):
        return self

    def invoke(self, _messages):
        return {"content": "DefaultCategory"}


@pytest.fixture
def sf_client_mock():
    class _DummyClient:
        # Configure with none existing appointments
        get_scheduled_appointments_async = AsyncMock(return_value=[])
        schedule_new_appointment_async = AsyncMock(return_value={"Id": "001"})
    return _DummyClient()


def _make_slot(start_dt: datetime, duration_minutes: int = 30):
    """Helper to build a fake Salesforce appointment dict."""
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    return {
        "Id": "EVT_TEST",
        "Subject": "Test Meeting",
        "Description": "Test",
        "StartDateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "EndDateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def format_date_for_comparison(date_str):
    """Helper to standardize date format for comparison."""
    return date_str


def test_duplicates_issue(sf_client_mock):
    """Test that the method doesn't return duplicate timeframes."""
    # Set up test data
    start_date = "2025-01-11T00:00:00Z"
    end_date = "2025-01-11T23:59:59Z"
    scheduled_slots = []
    
    # Call the method
    available_ranges = CalendarAgent.get_available_timeframes_from_scheduled_slots(
        start_date,
        end_date,
        scheduled_slots,
        max_weekday=6,  # Explicitly set max_weekday to include Saturday
        adjust_end_time=False,  # Use the original behavior without end time adjustment
    )
    
    # Debug output
    print(f"\nTest duplicates_issue:")
    print(f"Available ranges: {available_ranges}")
    print(f"Expected ranges: ['2025-01-11 09:00-12:00', '2025-01-11 13:00-18:00']\n")
    
    # Check for duplicates
    assert len(available_ranges) == len(set(available_ranges)), "Duplicate timeframes found in results"
    
    # Expected result with default availability timeframe [("09:00", "12:00"), ("13:00", "18:00")]
    expected_ranges = [
        "2025-01-11 09:00-12:00",
        "2025-01-11 13:00-18:00",
    ]
    
    assert sorted(available_ranges) == sorted(expected_ranges)


@pytest.mark.parametrize(
    "max_weekday,expected_ranges",
    [
        # Case 1: Include Saturday (max_weekday=6)
        (
            6,
            [
                "2025-01-11 09:00-12:00",  # Saturday morning
                "2025-01-11 13:00-18:00",  # Saturday afternoon
                "2025-01-13 09:00-12:00",  # Monday morning
                "2025-01-13 13:00-18:00",  # Monday afternoon
            ]
        ),
        # Case 2: Only weekdays (max_weekday=5), should exclude Saturday
        (
            5,
            [
                "2025-01-13 09:00-12:00",  # Monday morning
                "2025-01-13 13:00-18:00",  # Monday afternoon
            ]
        ),
        # Case 3: Include Sunday (max_weekday=7), should include all days
        (
            7,
            [
                "2025-01-11 09:00-12:00",  # Saturday morning
                "2025-01-11 13:00-18:00",  # Saturday afternoon
                "2025-01-12 09:00-12:00",  # Sunday morning
                "2025-01-12 13:00-18:00",  # Sunday afternoon
                "2025-01-13 09:00-12:00",  # Monday morning
                "2025-01-13 13:00-18:00",  # Monday afternoon
            ]
        ),
    ]
)
def test_multi_day_availability(sf_client_mock, max_weekday, expected_ranges):
    """Test multi-day availability with proper timeframes for different max_weekday values."""
    # Set up test data
    start_date = "2025-01-11T00:00:00Z"  # Saturday
    end_date = "2025-01-13T23:59:59Z"    # Monday
    scheduled_slots = []
    availability_timeframe = [("09:00", "12:00"), ("13:00", "18:00")]
    
    # Call the method
    available_ranges = CalendarAgent.get_available_timeframes_from_scheduled_slots(
        start_date,
        end_date,
        scheduled_slots,
        availability_timeframe=availability_timeframe,
        max_weekday=max_weekday,
        adjust_end_time=False,  # Use the original behavior without end time adjustment
    )
    
    # Check that we get the expected ranges for each day based on max_weekday
    assert sorted(available_ranges) == sorted(expected_ranges)


@pytest.mark.parametrize(
    "availability_timeframe, start_date, end_date, scheduled_slots, expected_ranges",
    [
        # 1. No taken slots – full morning and afternoon ranges available
        (
            [("9:00", "12:00"), ("13:00", "18:00")],
            "2025-01-06T00:00:00Z", "2025-01-06T23:59:59Z",
            [],
            [
                "2025-01-06 09:00-12:00",
                "2025-01-06 13:00-18:00",
            ],
        ),
        # 2. First slot taken (09:00-09:30) - morning range starts later
        (
            [("9:00", "12:00"), ("13:00", "18:00")],
            "2025-01-06T00:00:00Z", "2025-01-06T23:59:59Z",
            [_make_slot(datetime(2025, 1, 6, 9, 0))],
            [
                "2025-01-06 09:30-12:00",
                "2025-01-06 13:00-18:00",
            ],
        ),
        # 3. Custom opening hours 10–12 only
        (
            [("10:00", "12:00")],
            "2025-01-06T00:00:00Z", "2025-01-06T23:59:59Z",
            [],
            [
                "2025-01-06 10:00-12:00",
            ],
        ),
        # 4. Two consecutive taken slots 09:00 & 09:30 - morning range starts at 10:00
        (
            [("9:00", "12:00"), ("13:00", "18:00")],
            "2025-01-06T00:00:00Z", "2025-01-06T23:59:59Z",
            [
                _make_slot(datetime(2025, 1, 6, 9, 0), 30),
                _make_slot(datetime(2025, 1, 6, 9, 30), 30),
            ],
            [
                "2025-01-06 10:00-12:00",
                "2025-01-06 13:00-18:00",
            ],
        ),
        # 5. Overlapping appointments split morning availability
        (
            [("9:00", "12:00"), ("13:00", "18:00")],
            "2025-01-06T00:00:00Z", "2025-01-06T23:59:59Z",
            [
                _make_slot(datetime(2025, 1, 6, 10, 0), 45),
                _make_slot(datetime(2025, 1, 6, 10, 15), 45),
            ],
            [
                "2025-01-06 09:00-10:00",
                "2025-01-06 11:00-12:00",
                "2025-01-06 13:00-18:00",
            ],
        ),
        # 6. All slots taken within window – expect none for that timeframe
        (
            [("9:00", "10:00"), ("13:00", "18:00")],
            "2025-01-06T00:00:00Z", "2025-01-06T23:59:59Z",
            [
                _make_slot(datetime(2025, 1, 6, 9, 0)),
                _make_slot(datetime(2025, 1, 6, 9, 30)),
            ],
            [
                "2025-01-06 13:00-18:00",
            ],
        ),
        # 7. Friday to next Monday (weekend skip)
        (
            [("9:00", "10:00")],
            "2025-01-10T00:00:00Z",  # Friday
            "2025-01-13T23:59:59Z",  # Monday
            [],
            [
                "2025-01-10 09:00-10:00",
                "2025-01-13 09:00-10:00",
            ],
        ),
        # 8. Multiple appointments creating fragmented availability
        (
            [("9:00", "18:00")],
            "2025-01-06T00:00:00Z", "2025-01-06T23:59:59Z",
            [
                _make_slot(datetime(2025, 1, 6, 10, 0), 60),  # 10:00-11:00
                _make_slot(datetime(2025, 1, 6, 13, 0), 60),  # 13:00-14:00
                _make_slot(datetime(2025, 1, 6, 16, 0), 60),  # 16:00-17:00
            ],
            [
                "2025-01-06 09:00-10:00",
                "2025-01-06 11:00-13:00",
                "2025-01-06 14:00-16:00",
                "2025-01-06 17:00-18:00",
            ],
        ),
        # 9. Test for duplicate timeframes issue
        (
            [("9:00", "12:00"), ("13:00", "18:00")],
            "2025-01-10T00:00:00Z", "2025-01-10T23:59:59Z",
            [],
            [
                "2025-01-10 09:00-12:00",
                "2025-01-10 13:00-18:00",
            ],
        ),
        # 10. Test for proper handling of multiple availability timeframes
        (
            [("9:00", "12:00"), ("13:00", "18:00")],
            "2025-01-10T00:00:00Z", "2025-01-10T23:59:59Z",
            [_make_slot(datetime(2025, 1, 11, 11, 30), 30)],  # 11:30-12:00
            [
                "2025-01-10 09:00-12:00",
                "2025-01-10 13:00-18:00",
            ],
        ),
        # 11. Test for proper handling of availability timeframes with overlapping slots
        (
            [("9:00", "12:00"), ("13:00", "18:00")],
            "2025-01-10T00:00:00Z", "2025-01-10T23:59:59Z",
            [_make_slot(datetime(2025, 1, 11, 11, 30), 90)],  # 11:30-13:00 (overlaps lunch break)
            [
                "2025-01-10 09:00-12:00",
                "2025-01-10 13:00-18:00",
            ],
        ),
        # 12. Test for proper handling of default availability timeframes
        (
            None,  # Use default availability timeframe
            "2025-01-10T00:00:00Z", "2025-01-10T23:59:59Z",
            [],
            [
                "2025-01-10 09:00-12:00",
                "2025-01-10 13:00-18:00",
            ],
        ),
        # 13. Test for multi-day availability with default timeframes
        (
            None,  # Use default availability timeframe
            "2025-01-10T00:00:00Z", "2025-01-13T23:59:59Z",  # Saturday to Monday
            [],
            [
                "2025-01-10 09:00-12:00",
                "2025-01-10 13:00-18:00",
                "2025-01-13 09:00-12:00",
                "2025-01-13 13:00-18:00",
            ],
        ),
    ],
)
def test_get_available_timeframes_with_scheduled_slots(
    availability_timeframe,
    start_date,
    end_date,
    scheduled_slots,
    expected_ranges,
):
    """Verify CalendarAgent.get_available_slots_from_scheduled_ones with consolidated time ranges."""
    available_ranges = CalendarAgent.get_available_timeframes_from_scheduled_slots(
                            start_date,
                            end_date,
                            scheduled_slots,
                            availability_timeframe=availability_timeframe,
                            adjust_end_time=False,  # Use the native behavior without end time adjustment
                        )

    # Sort both lists to ensure consistent comparison regardless of order
    assert sorted(available_ranges) == sorted(expected_ranges)


@pytest.mark.parametrize(
    "slot_duration, availability_timeframe, expected_ranges",
    [
        # Test with 15-minute slot duration
        (
            15,
            [("9:00", "12:00"), ("13:00", "18:00")],
            [
                "2025-01-06 09:00-11:45",
                "2025-01-06 13:00-17:45",
            ],
        ),
        # Test with 30-minute slot duration (default)
        (
            30,
            [("9:00", "12:00"), ("13:00", "18:00")],
            [
                "2025-01-06 09:00-11:30",
                "2025-01-06 13:00-17:30",
            ],
        ),
        # Test with 45-minute slot duration
        (
            45,
            [("9:00", "12:00"), ("13:00", "18:00")],
            [
                "2025-01-06 09:00-11:15",
                "2025-01-06 13:00-17:15",
            ],
        ),
        # Test with 60-minute slot duration
        (
            60,
            [("9:00", "12:00"), ("13:00", "18:00")],
            [
                "2025-01-06 09:00-11:00",
                "2025-01-06 13:00-17:00",
            ],
        ),
        # Test with 90-minute slot duration
        (
            90,
            [("9:00", "12:00"), ("13:00", "18:00")],
            [
                "2025-01-06 09:00-10:30",
                "2025-01-06 13:00-16:30",
            ],
        ),
        # Test with 120-minute slot duration
        (
            120,
            [("9:00", "12:00"), ("13:00", "18:00")],
            [
                "2025-01-06 09:00-10:00",
                "2025-01-06 13:00-16:00",
            ],
        ),
        # Test with odd timeframes and 30-minute slot duration
        (
            30,
            [("8:15", "10:45"), ("11:30", "13:00"), ("14:45", "17:30")],
            [
                "2025-01-06 08:15-10:15",
                "2025-01-06 11:30-12:30",
                "2025-01-06 14:45-17:00",
            ],
        ),
        # Test with a timeframe that is exactly one slot long
        (
            30,
            [("9:00", "9:30")],
            ["2025-01-06 09:00-09:00"],  # Expect a single slots at 9am
        ),
        # Test with a timeframe with slots, and one already taken
        (
            45,
            [("9:00", "9:30")],
            [],  # Expect no slots
        ),
    ],
)
def test_get_available_timeframes_with_adjust_end_time(
    sf_client_mock, slot_duration, availability_timeframe, expected_ranges
):
    """Test that the end time of availability timeframes is correctly adjusted based on slot duration."""
    # Set up test data
    start_date = "2025-01-06T00:00:00Z"  # Monday
    end_date = "2025-01-06T23:59:59Z"    # Monday
    scheduled_slots = []  # No taken slots to focus on the slot duration adjustment
    
    # Call the method
    available_ranges = CalendarAgent.get_available_timeframes_from_scheduled_slots(
        start_date,
        end_date,
        scheduled_slots,
        slot_duration_minutes=slot_duration,
        availability_timeframe=availability_timeframe,
        adjust_end_time=True,  # Enable the slot duration adjustment, object of this test
    )
    
    # Sort both lists to ensure consistent comparison regardless of order
    assert sorted(available_ranges) == sorted(expected_ranges)
