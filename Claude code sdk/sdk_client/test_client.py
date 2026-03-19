"""
Unit tests for Claude Code SDK Client.

Run tests with:
    pytest cc/test_client.py -v

Or with coverage:
    pytest cc/test_client.py -v --cov=cc
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from client import (
    ClaudeClient,
    ClaudeAgentOptions,
    ClaudeSession,
    AgentMessage,
    PermissionMode,
    ANALYSIS_TOOLS,
    EDIT_TOOLS,
    FULL_TOOLS,
)


class TestPermissionMode:
    """Tests for PermissionMode enum."""

    def test_permission_mode_values(self):
        assert PermissionMode.DEFAULT.value == "default"
        assert PermissionMode.ACCEPT_EDITS.value == "acceptEdits"
        assert PermissionMode.BYPASS.value == "bypassPermissions"

    def test_permission_mode_string_conversion(self):
        assert str(PermissionMode.DEFAULT) == "PermissionMode.DEFAULT"
        assert PermissionMode.ACCEPT_EDITS == "acceptEdits"


class TestToolSets:
    """Tests for predefined tool sets."""

    def test_analysis_tools_are_read_only(self):
        assert "Read" in ANALYSIS_TOOLS
        assert "Glob" in ANALYSIS_TOOLS
        assert "Grep" in ANALYSIS_TOOLS
        assert "Edit" not in ANALYSIS_TOOLS
        assert "Write" not in ANALYSIS_TOOLS
        assert "Bash" not in ANALYSIS_TOOLS

    def test_edit_tools_include_write_operations(self):
        assert "Read" in EDIT_TOOLS
        assert "Edit" in EDIT_TOOLS
        assert "Write" in EDIT_TOOLS
        assert "Bash" not in EDIT_TOOLS

    def test_full_tools_include_all(self):
        assert "Read" in FULL_TOOLS
        assert "Edit" in FULL_TOOLS
        assert "Write" in FULL_TOOLS
        assert "Bash" in FULL_TOOLS
        assert "WebSearch" in FULL_TOOLS
        assert "WebFetch" in FULL_TOOLS


class TestClaudeAgentOptions:
    """Tests for ClaudeAgentOptions configuration."""

    def test_default_options(self):
        options = ClaudeAgentOptions()
        assert options.allowed_tools == EDIT_TOOLS
        assert options.permission_mode == PermissionMode.ACCEPT_EDITS
        assert options.max_turns is None
        assert options.system_prompt is None
        assert options.mcp_servers is None
        assert options.working_directory is None

    def test_custom_options(self):
        options = ClaudeAgentOptions(
            allowed_tools=ANALYSIS_TOOLS,
            permission_mode=PermissionMode.BYPASS,
            max_turns=10,
            system_prompt="You are a code reviewer.",
            working_directory="/tmp/test"
        )
        assert options.allowed_tools == ANALYSIS_TOOLS
        assert options.permission_mode == PermissionMode.BYPASS
        assert options.max_turns == 10
        assert options.system_prompt == "You are a code reviewer."
        assert options.working_directory == "/tmp/test"

    @patch("client.SDK_AVAILABLE", True)
    @patch("client.SDKOptions")
    def test_to_sdk_options_conversion(self, mock_sdk_options):
        options = ClaudeAgentOptions(
            allowed_tools=["Read", "Glob"],
            permission_mode=PermissionMode.DEFAULT,
            max_turns=5,
            system_prompt="Test prompt",
            working_directory="/test"
        )
        options.to_sdk_options()

        mock_sdk_options.assert_called_once_with(
            allowed_tools=["Read", "Glob"],
            permission_mode="default",
            max_turns=5,
            system_prompt="Test prompt",
            mcp_servers=None,
            cwd="/test"
        )

    @patch("client.SDK_AVAILABLE", False)
    def test_to_sdk_options_raises_when_sdk_unavailable(self):
        options = ClaudeAgentOptions()
        with pytest.raises(RuntimeError, match="claude-agent-sdk is not installed"):
            options.to_sdk_options()


class TestAgentMessage:
    """Tests for AgentMessage data class."""

    def test_text_message_creation(self):
        msg = AgentMessage(type="text", content="Hello world")
        assert msg.type == "text"
        assert msg.content == "Hello world"
        assert msg.tool_name is None
        assert msg.raw is None

    def test_tool_use_message_creation(self):
        msg = AgentMessage(
            type="tool_use",
            content='{"path": "test.py"}',
            tool_name="Read"
        )
        assert msg.type == "tool_use"
        assert msg.tool_name == "Read"

    def test_result_message_creation(self):
        msg = AgentMessage(type="result", content="success")
        assert msg.type == "result"
        assert msg.content == "success"

    @patch("client.SDK_AVAILABLE", False)
    def test_from_sdk_message_returns_none_when_sdk_unavailable(self):
        result = AgentMessage.from_sdk_message(MagicMock())
        assert result is None


class TestClaudeSession:
    """Tests for ClaudeSession multi-turn conversations."""

    @pytest.fixture
    def mock_sdk_client(self):
        client = AsyncMock()
        return client

    @pytest.fixture
    def session(self, mock_sdk_client):
        options = ClaudeAgentOptions()
        return ClaudeSession(mock_sdk_client, options)

    @pytest.mark.asyncio
    async def test_asend_calls_client_query(self, session, mock_sdk_client):
        await session.asend("Test prompt")
        mock_sdk_client.query.assert_called_once_with("Test prompt")

    @pytest.mark.asyncio
    @patch("client.AgentMessage.from_sdk_message")
    async def test_areceive_yields_messages(
        self, mock_from_sdk, session, mock_sdk_client
    ):
        mock_message = AgentMessage(type="text", content="Response")
        mock_from_sdk.return_value = mock_message

        mock_sdk_client.receive_response = AsyncMock(
            return_value=self._async_gen([MagicMock()])
        )

        messages = []
        async for msg in session.areceive():
            messages.append(msg)

        assert len(messages) == 1
        assert messages[0].content == "Response"

    @pytest.mark.asyncio
    @patch("client.AgentMessage.from_sdk_message")
    async def test_aquery_sends_and_receives(
        self, mock_from_sdk, session, mock_sdk_client
    ):
        mock_message = AgentMessage(type="text", content="Response")
        mock_from_sdk.return_value = mock_message

        mock_sdk_client.receive_response = AsyncMock(
            return_value=self._async_gen([MagicMock()])
        )

        messages = []
        async for msg in session.aquery("Test"):
            messages.append(msg)

        mock_sdk_client.query.assert_called_once_with("Test")
        assert len(messages) == 1

    @staticmethod
    async def _async_gen(items):
        for item in items:
            yield item


class TestClaudeClient:
    """Tests for ClaudeClient main class."""

    @patch("client.SDK_AVAILABLE", False)
    def test_init_raises_when_sdk_unavailable(self):
        with pytest.raises(RuntimeError, match="claude-agent-sdk is not installed"):
            ClaudeClient()

    @patch("client.SDK_AVAILABLE", True)
    def test_init_with_default_options(self):
        client = ClaudeClient()
        assert client._default_options is not None
        assert client._default_options.allowed_tools == EDIT_TOOLS

    @patch("client.SDK_AVAILABLE", True)
    def test_init_with_custom_options(self):
        custom_options = ClaudeAgentOptions(
            allowed_tools=ANALYSIS_TOOLS,
            permission_mode=PermissionMode.BYPASS
        )
        client = ClaudeClient(default_options=custom_options)
        assert client._default_options.allowed_tools == ANALYSIS_TOOLS
        assert client._default_options.permission_mode == PermissionMode.BYPASS

    @patch("client.SDK_AVAILABLE", True)
    def test_check_sdk_available(self):
        assert ClaudeClient.check_sdk_available() is True

    @patch("client.SDK_AVAILABLE", False)
    def test_check_sdk_unavailable(self):
        assert ClaudeClient.check_sdk_available() is False

    @pytest.mark.asyncio
    @patch("client.SDK_AVAILABLE", True)
    @patch("client.sdk_query")
    @patch("client.AgentMessage.from_sdk_message")
    async def test_aquery_iterates_messages(self, mock_from_sdk, mock_sdk_query):
        mock_message = AgentMessage(type="text", content="Test response")
        mock_from_sdk.return_value = mock_message

        async def async_gen():
            yield MagicMock()

        mock_sdk_query.return_value = async_gen()

        client = ClaudeClient()
        messages = []
        async for msg in client.aquery("Test prompt"):
            messages.append(msg)

        assert len(messages) == 1
        assert messages[0].content == "Test response"

    @pytest.mark.asyncio
    @patch("client.SDK_AVAILABLE", True)
    @patch("client.sdk_query")
    @patch("client.AgentMessage.from_sdk_message")
    async def test_aquery_simple_returns_combined_text(
        self, mock_from_sdk, mock_sdk_query
    ):
        mock_from_sdk.side_effect = [
            AgentMessage(type="text", content="Line 1"),
            AgentMessage(type="text", content="Line 2"),
            AgentMessage(type="tool_use", content="{}", tool_name="Read"),
        ]

        async def async_gen():
            yield MagicMock()
            yield MagicMock()
            yield MagicMock()

        mock_sdk_query.return_value = async_gen()

        client = ClaudeClient()
        result = await client.aquery_simple("Test prompt")

        assert "Line 1" in result
        assert "Line 2" in result

    @pytest.mark.asyncio
    @patch("client.SDK_AVAILABLE", True)
    @patch("client.ClaudeSDKClient")
    async def test_asession_context_manager(self, mock_sdk_client_class):
        mock_sdk_client = AsyncMock()
        mock_sdk_client_class.return_value.__aenter__.return_value = mock_sdk_client
        mock_sdk_client_class.return_value.__aexit__.return_value = None

        client = ClaudeClient()

        async with client.asession() as session:
            assert isinstance(session, ClaudeSession)


class TestIntegration:
    """Integration tests (require SDK to be installed)."""

    @pytest.mark.skipif(
        not ClaudeClient.check_sdk_available(),
        reason="Claude SDK not installed"
    )
    @pytest.mark.asyncio
    async def test_real_query_execution(self):
        """
        Integration test that runs a real query.
        Only runs if SDK is installed and API key is configured.
        """
        client = ClaudeClient()
        options = ClaudeAgentOptions(
            allowed_tools=ANALYSIS_TOOLS,
            max_turns=1
        )

        messages = []
        async for msg in client.aquery("Say 'test successful'", options):
            messages.append(msg)

        assert len(messages) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
