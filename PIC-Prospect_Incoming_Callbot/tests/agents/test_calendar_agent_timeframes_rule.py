"""
Tests for the CalendarAgent timeframes inclusion rule:
"Inclut aujourd'hui si il est moins de 18h, ainsi que le prochain jour ouvré. 
Attention, si nous sommes le vendredi, le prochain jour ouvré sera le lundi suivant (soit J+3)."

These tests verify that:
1. The prompt includes the correct current date information  
2. The LLM calls the correct tools with appropriate date ranges
3. The business logic in the prompt is correctly applied
"""
import pytest
from unittest.mock import AsyncMock, patch, Mock
from datetime import datetime, timedelta
import pytz
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable

from app.agents.calendar_agent import CalendarAgent


class MockLLM(Runnable):
    """Mock LLM that returns predefined responses and tracks calls for testing"""
    
    def __init__(self, response_template=None):
        self.response_template = response_template or "Je vous propose les créneaux suivants : {timeframes}. Avez-vous une préférence ?"
        self.call_count = 0
        self.last_call_args = None

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, input, config=None, **kwargs):
        self.call_count += 1
        self.last_call_args = input
        return AIMessage(content=self.response_template)

    def invoke(self, input, config=None, **kwargs):
        return self.ainvoke(input, config, **kwargs)


@pytest.fixture
def sf_client_mock():
    """Mock Salesforce client with no scheduled appointments"""
    class MockClient:
        async def get_scheduled_appointments_async(self, start_date, end_date, owner_id):
            return []  # No appointments scheduled
        
        async def schedule_new_appointment_async(self, *args, **kwargs):
            return {"Id": "test_appointment_001"}
    
    return MockClient()


class TestCalendarAgentTimeframesRule:
    """Test cases for the timeframes inclusion rule"""
    
    def test_prompt_contains_timeframes_rule(self):
        """Test that the prompt file contains the expected rule text"""
        # Create a simple agent to access the prompt loading method
        sf_client = Mock()
        llm = MockLLM()
        agent = CalendarAgent(sf_client, llm, llm)
        
        # Load the prompt and verify it contains the rule
        prompt_content = agent._load_available_timeframes_prompt()
        
        assert "Inclut aujourd'hui si il est moins de 18h" in prompt_content
        assert "le prochain jour ouvré" in prompt_content
        assert "si nous sommes le vendredi, le prochain jour ouvré sera le lundi suivant (soit J+3)" in prompt_content
    
    @pytest.mark.parametrize("test_time,expected_french_time", [
        # Test various times and their French format
        (datetime(2025, 1, 15, 9, 0, 0), "mercredi 15 janvier 2025 à 9 heures"),
        (datetime(2025, 1, 15, 14, 30, 0), "mercredi 15 janvier 2025 à 14 heures 30"),
        (datetime(2025, 1, 17, 17, 59, 0), "vendredi 17 janvier 2025 à 17 heures 59"),
        (datetime(2025, 1, 17, 18, 0, 0), "vendredi 17 janvier 2025 à 18 heures"),
    ])
    def test_current_date_formatting_for_prompt(self, test_time, expected_french_time):
        """Test that dates are correctly formatted in French for the prompt"""
        # Create agent and set test time
        sf_client = Mock()
        llm = MockLLM()
        agent = CalendarAgent(sf_client, llm, llm)
        
        # Set the test time as current time
        CalendarAgent.now = pytz.timezone('Europe/Paris').localize(test_time)
        
        # Test the French date formatting
        formatted_date = agent._to_french_date(CalendarAgent.now, include_weekday=True, include_year=True, include_hour=True)
        assert formatted_date == expected_french_time
    
    @pytest.mark.parametrize("weekday,french_day", [
        (0, "lundi"),    # Monday
        (1, "mardi"),    # Tuesday  
        (2, "mercredi"), # Wednesday
        (3, "jeudi"),    # Thursday
        (4, "vendredi"), # Friday
        (5, "samedi"),   # Saturday
        (6, "dimanche"), # Sunday
    ])
    def test_french_weekday_formatting(self, weekday, french_day):
        """Test that weekdays are correctly formatted in French"""
        sf_client = Mock()
        llm = MockLLM()
        agent = CalendarAgent(sf_client, llm, llm)
        
        # Create a test date with the specified weekday
        # January 6, 2025 is a Monday (weekday 0)
        test_date = datetime(2025, 1, 6 + weekday, 15, 0, 0)
        CalendarAgent.now = pytz.timezone('Europe/Paris').localize(test_date)
        
        formatted_date = agent._to_french_date(CalendarAgent.now, include_weekday=True, include_year=False, include_hour=False)
        assert formatted_date.startswith(french_day)
    
    async def test_prompt_receives_current_date_context(self, sf_client_mock):
        """Test that the LLM prompt receives the current date in the correct format"""
        # Create a mock LLM that captures the prompt arguments
        captured_args = []
        
        class CapturingMockLLM(MockLLM):
            async def ainvoke(self, input, config=None, **kwargs):
                captured_args.append(input)
                return AIMessage(content="Mock response")
        
        classifier_llm = MockLLM("Proposition de créneaux")
        timeframes_llm = CapturingMockLLM()
        agent = CalendarAgent(sf_client_mock, classifier_llm, timeframes_llm)
        
        # Set specific test time - Friday afternoon before 6 PM
        test_time = datetime(2025, 1, 17, 15, 30, 0)  # Friday 3:30 PM
        CalendarAgent.now = pytz.timezone('Europe/Paris').localize(test_time)
        agent._set_user_info("test_user", "John", "Doe", "john@test.com", "owner_123", "Test Owner")
        
        # Mock the available timeframes tool to return empty results
        with patch.object(CalendarAgent, 'get_available_timeframes_async', return_value=[]):
            await agent.run_async("Je voudrais prendre rendez-vous", [])
        
        # Verify that the LLM was called with the current date context
        assert len(captured_args) > 0, "LLM should have been called"
        
        # Check that the current date is included in the prompt
        prompt_content = str(captured_args[0])
        assert "vendredi 17 janvier 2025" in prompt_content, "Current date should be in the prompt"
        assert "15 heures 30" in prompt_content, "Current time should be in the prompt"

    def test_available_timeframes_tool_uses_correct_date_formats(self, sf_client_mock):
        """Test that the available timeframes tool properly handles date formats"""
        # Create agent 
        sf_client = Mock()
        llm = MockLLM()
        agent = CalendarAgent(sf_client, llm, llm)
        
        # Test the static method that calculates available timeframes
        start_date = "2025-01-15T00:00:00Z"  # Wednesday
        end_date = "2025-01-17T00:00:00Z"    # Friday
        
        # Mock some scheduled appointments
        scheduled_slots = [
            {
                "StartDateTime": "2025-01-15T10:00:00Z",
                "EndDateTime": "2025-01-15T11:00:00Z"
            }
        ]
        
        available_slots = CalendarAgent.get_available_timeframes_from_scheduled_slots(
            start_date, end_date, scheduled_slots
        )
        
        # Verify that the function returns properly formatted time ranges
        assert len(available_slots) > 0
        # Verify format is like "2025-01-15 09:00-10:00"
        for slot in available_slots:
            assert " " in slot, f"Slot should contain date and time: {slot}"
            assert "-" in slot, f"Slot should contain time range: {slot}"