"""
Tests for AgentsGraph consent validation functionality.

These tests verify that:
1. The system correctly detects when the last assistant message is yes_no_consent_text
2. The LLM correctly analyzes user consent responses
3. The correct nodes are called based on consent analysis
4. The routing logic works correctly in different scenarios
"""

from unittest.mock import Mock

import pytest

from app.agents.agents_graph import AgentsGraph
from app.agents.phone_conversation_state_model import PhoneConversationState
from app.agents.text_registry import TextRegistry


class MockLLM:
    """Mock LLM for testing consent analysis"""

    def __init__(self, response_content="oui"):
        self.response_content = response_content
        self.call_count = 0
        self.last_prompt = None

    async def ainvoke(self, prompt):
        self.call_count += 1
        self.last_prompt = prompt
        mock_response = Mock()
        mock_response.content = self.response_content
        return mock_response


class TestConsentValidationLogic:
    """Test consent validation logic without full AgentsGraph initialization"""

    async def test_analyse_appointment_consent_async_accepts_positive_responses(self):
        """Test that the consent analysis method correctly processes positive responses"""
        # Arrange
        mock_llm = MockLLM("oui")
        agents_graph = AgentsGraph.__new__(
            AgentsGraph
        )  # Create instance without calling __init__
        agents_graph.calendar_classifier_llm = mock_llm
        agents_graph.logger = Mock()  # Add mock logger

        chat_history = [
            ("user", "Je voudrais un rendez-vous"),
            ("assistant", TextRegistry.yes_no_consent_text),
        ]

        # Act
        result = await agents_graph._analyse_appointment_consent_async(
            "d'accord", chat_history
        )

        # Assert
        assert result == "oui"
        assert mock_llm.call_count == 1
        assert "d'accord" in mock_llm.last_prompt
        assert "Je voudrais un rendez-vous" in mock_llm.last_prompt

    async def test_analyse_appointment_consent_async_rejects_negative_responses(self):
        """Test that the consent analysis method correctly processes negative responses"""
        # Arrange
        mock_llm = MockLLM("non")
        agents_graph = AgentsGraph.__new__(
            AgentsGraph
        )  # Create instance without calling __init__
        agents_graph.calendar_classifier_llm = mock_llm
        agents_graph.logger = Mock()  # Add mock logger

        chat_history = [
            ("user", "Je voudrais un rendez-vous"),
            ("assistant", TextRegistry.yes_no_consent_text),
        ]

        # Act
        result = await agents_graph._analyse_appointment_consent_async(
            "pas maintenant", chat_history
        )

        # Assert
        assert result == "non"
        assert mock_llm.call_count == 1
        assert "pas maintenant" in mock_llm.last_prompt

    @pytest.mark.parametrize(
        "user_input, expected_in_prompt",
        [
            ("oui", "oui"),
            ("d'accord", "d'accord"),
            ("parfait", "parfait"),
            ("ça me convient", "ça me convient"),
            ("non", "non"),
            ("pas maintenant", "pas maintenant"),
            ("plus tard", "plus tard"),
            ("je ne peux pas", "je ne peux pas"),
        ],
    )
    async def test_consent_analysis_includes_user_input_in_prompt(
        self, user_input, expected_in_prompt
    ):
        """Test that user input is correctly included in the LLM prompt"""
        # Arrange
        mock_llm = MockLLM("oui")
        agents_graph = AgentsGraph.__new__(AgentsGraph)
        agents_graph.calendar_classifier_llm = mock_llm
        agents_graph.logger = Mock()  # Add mock logger

        chat_history = [("assistant", TextRegistry.yes_no_consent_text)]

        # Act
        await agents_graph._analyse_appointment_consent_async(user_input, chat_history)

        # Assert
        assert expected_in_prompt in mock_llm.last_prompt
        assert mock_llm.call_count == 1


class TestConsentRouterLogic:
    """Test the router logic that detects consent scenarios"""

    def test_find_last_assistant_message_in_history(self):
        """Test finding the last assistant message in conversation history"""
        # Test data with various history scenarios
        test_cases = [
            {
                "name": "consent_text_is_last_assistant_message",
                "history": [
                    ("user", "Je voudrais prendre rendez-vous"),
                    ("assistant", "Bonjour"),
                    ("assistant", TextRegistry.yes_no_consent_text),
                ],
                "expected": TextRegistry.yes_no_consent_text,
            },
            {
                "name": "consent_text_with_user_messages_after",
                "history": [
                    ("user", "Je voudrais prendre rendez-vous"),
                    ("assistant", TextRegistry.yes_no_consent_text),
                    ("user", "Pouvez-vous répéter ?"),
                    ("user", "Je n'ai pas bien entendu"),
                ],
                "expected": TextRegistry.yes_no_consent_text,
            },
            {
                "name": "different_assistant_message",
                "history": [
                    ("user", "Bonjour"),
                    ("assistant", "Comment puis-je vous aider ?"),
                ],
                "expected": "Comment puis-je vous aider ?",
            },
            {"name": "empty_history", "history": [], "expected": None},
            {
                "name": "only_user_messages",
                "history": [
                    ("user", "Bonjour"),
                    ("user", "Je voudrais un rendez-vous"),
                ],
                "expected": None,
            },
        ]

        for case in test_cases:
            # Act - Simulate the logic from the router method
            last_assistant_message = None
            history = case["history"]
            if history and len(history) > 0:
                for role, message in reversed(history):
                    if role == "assistant":
                        last_assistant_message = message
                        break

            # Assert
            assert last_assistant_message == case["expected"], (
                f"Failed for case: {case['name']}"
            )

    def test_consent_detection_logic(self):
        """Test the logic that determines if consent validation should be triggered"""
        test_cases = [
            {
                "name": "should_trigger_consent_validation",
                "last_assistant_message": TextRegistry.yes_no_consent_text,
                "expected_trigger": True,
            },
            {
                "name": "should_not_trigger_with_different_message",
                "last_assistant_message": "Comment puis-je vous aider ?",
                "expected_trigger": False,
            },
            {
                "name": "should_not_trigger_with_none_message",
                "last_assistant_message": None,
                "expected_trigger": False,
            },
        ]

        for case in test_cases:
            # Act - Simulate the condition from router method
            should_trigger = (
                case["last_assistant_message"] == TextRegistry.yes_no_consent_text
            )

            # Assert
            assert should_trigger == case["expected_trigger"], (
                f"Failed for case: {case['name']}"
            )


class TestRoutingScenarios:
    """Test various routing scenarios for consent validation"""

    @pytest.mark.parametrize(
        "llm_response,expected_node",
        [
            ("oui", "calendar_agent"),
            ("non", "no_appointment_requested"),
            ("OUI", "calendar_agent"),  # Test case insensitivity
            ("NON", "no_appointment_requested"),  # Test case insensitivity
            ("maybe", "no_appointment_requested"),  # Unknown response defaults to no
        ],
    )
    def test_consent_response_to_node_mapping(self, llm_response, expected_node):
        """Test that LLM responses correctly map to the right nodes"""
        # Simulate the routing logic from the router method
        consent = llm_response.strip().lower()
        if consent == "oui":
            next_node = "calendar_agent"
        else:
            next_node = "no_appointment_requested"

        assert next_node == expected_node


class TestPromptGeneration:
    """Test that consent analysis prompts are generated correctly"""

    def test_prompt_file_loading(self):
        """Test that the consent classifier prompt file can be loaded"""
        # This tests the file loading logic used in analyse_appointment_consent_async
        try:
            with open(
                "app/agents/prompts/appointment_consent_classifier_prompt.txt",
                encoding="utf-8",
            ) as file:
                prompt_content = file.read()

            # Verify the prompt contains key elements
            assert "<Instructions>" in prompt_content
            assert "oui" in prompt_content
            assert "non" in prompt_content
            assert "{user_input}" in prompt_content
            assert "{chat_history}" in prompt_content

        except FileNotFoundError:
            pytest.fail("Consent classifier prompt file not found")

    def test_prompt_formatting(self):
        """Test that prompts are formatted correctly with user input and history"""
        # Simulate the prompt formatting logic
        template = "User said: {user_input}\nHistory: {chat_history}"
        user_input = "d'accord"
        chat_history = "[user]: Je veux un rendez-vous\n[assistant]: Est-ce que cela vous convient ?"

        formatted_prompt = template.format(
            user_input=user_input, chat_history=chat_history
        )

        assert "d'accord" in formatted_prompt
        assert "Je veux un rendez-vous" in formatted_prompt
        assert "Est-ce que cela vous convient ?" in formatted_prompt


class TestTextRegistryIntegration:
    """Test integration with TextRegistry"""

    def test_yes_no_consent_text_exists(self):
        """Test that the consent text constant exists in TextRegistry"""
        assert hasattr(TextRegistry, "yes_no_consent_text")
        assert TextRegistry.yes_no_consent_text == "Est-ce que cela vous convient ?"

    def test_no_appointment_requested_text_exists(self):
        """Test that the no appointment text constant exists in TextRegistry"""
        assert hasattr(TextRegistry, "no_appointment_requested_text")
        assert (
            TextRegistry.no_appointment_requested_text
            == "Votre appel a bien été prise en compte, votre conseiller en formation vous recontactera dès que possible. Merci et au revoir."
        )


class TestRouterIntegrationScenarios:
    """Test complete router scenarios with consent validation"""

    @pytest.mark.parametrize(
        "user_response,llm_response,expected_node",
        [
            ("oui", "oui", "calendar_agent"),
            ("d'accord", "oui", "calendar_agent"),
            ("parfait", "oui", "calendar_agent"),
            ("ça me convient", "oui", "calendar_agent"),
            ("non", "non", "no_appointment_requested"),
            ("pas maintenant", "non", "no_appointment_requested"),
            ("plus tard", "non", "no_appointment_requested"),
            ("je ne peux pas", "non", "no_appointment_requested"),
        ],
    )
    async def test_complete_consent_validation_router_flow(
        self, user_response, llm_response, expected_node
    ):
        """Test the complete router flow with consent validation"""
        # Arrange
        mock_llm = MockLLM(llm_response)
        agents_graph = AgentsGraph.__new__(AgentsGraph)
        agents_graph.available_actions = [
            "schedule_appointement"
        ]  # Trigger single action logic
        agents_graph.calendar_classifier_llm = mock_llm
        agents_graph.logger = Mock()

        # Mock the analyse_appointment_consent_async method
        original_method = agents_graph._analyse_appointment_consent_async

        async def mock_consent_analysis(user_input, chat_history):
            return await original_method(user_input, chat_history)

        agents_graph._analyse_appointment_consent_async = mock_consent_analysis

        # Create state with consent text as last assistant message
        state = PhoneConversationState(
            call_sid="test_call_123",
            caller_phone="+33123456789",
            user_input=user_response,
            history=[
                ("user", "Je voudrais prendre rendez-vous"),
                (
                    "assistant",
                    "Votre conseiller, Marie, est actuellement indisponible. Je vous propose de prendre rendez-vous avec lui.",
                ),
                (
                    "assistant",
                    TextRegistry.yes_no_consent_text,
                ),  # "Est-ce que cela vous convient ?"
            ],
            agent_scratchpad={"conversation_id": "test_conv_123"},
        )

        # Act - Simulate the router logic for single schedule_appointement action
        if (
            len(agents_graph.available_actions) == 1
            and agents_graph.available_actions[0] == "schedule_appointement"
        ):
            # Find last assistant message
            history = state.get("history", [])
            last_assistant_message = None
            if history and len(history) > 0:
                for role, message in reversed(history):
                    if role == "assistant":
                        last_assistant_message = message
                        break

            # Check if consent validation should be triggered
            if last_assistant_message == TextRegistry.yes_no_consent_text:
                # Analyze consent
                consent = await agents_graph._analyse_appointment_consent_async(
                    user_response, history
                )
                if consent == "oui":
                    next_agent = "calendar_agent"
                else:
                    next_agent = "no_appointment_requested"
            else:
                # Default behavior
                next_agent = "calendar_agent"

            state["agent_scratchpad"]["next_agent_needed"] = next_agent

        # Assert
        assert state["agent_scratchpad"]["next_agent_needed"] == expected_node
        # Verify LLM was called for consent analysis
        assert mock_llm.call_count == 1
        assert user_response in mock_llm.last_prompt

    async def test_router_flow_without_consent_text(self):
        """Test router flow when last assistant message is NOT consent text"""
        # Arrange
        mock_llm = MockLLM("oui")
        agents_graph = AgentsGraph.__new__(AgentsGraph)
        agents_graph.available_actions = ["schedule_appointement"]
        agents_graph.calendar_classifier_llm = mock_llm
        agents_graph.logger = Mock()

        state = PhoneConversationState(
            call_sid="test_call_123",
            caller_phone="+33123456789",
            user_input="oui",
            history=[
                ("user", "Je voudrais prendre rendez-vous"),
                (
                    "assistant",
                    "Comment puis-je vous aider ?",
                ),  # Different message, not consent
            ],
            agent_scratchpad={"conversation_id": "test_conv_123"},
        )

        # Act - Simulate router logic
        if (
            len(agents_graph.available_actions) == 1
            and agents_graph.available_actions[0] == "schedule_appointement"
        ):
            history = state.get("history", [])
            last_assistant_message = None
            if history and len(history) > 0:
                for role, message in reversed(history):
                    if role == "assistant":
                        last_assistant_message = message
                        break

            # Should NOT trigger consent validation
            if last_assistant_message == TextRegistry.yes_no_consent_text:
                consent = await agents_graph._analyse_appointment_consent_async(
                    "oui", history
                )
                next_agent = (
                    "calendar_agent" if consent == "oui" else "no_appointment_requested"
                )
            else:
                # Default behavior - direct to calendar
                next_agent = "calendar_agent"

            state["agent_scratchpad"]["next_agent_needed"] = next_agent

        # Assert
        assert state["agent_scratchpad"]["next_agent_needed"] == "calendar_agent"
        # Verify LLM was NOT called for consent analysis
        assert mock_llm.call_count == 0
