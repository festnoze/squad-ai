"""
Claude Code SDK Client

A Python client wrapper exposing essential features of the Claude Code SDK.
Provides simplified interfaces for common agent operations.

Usage:
    from cc import ClaudeClient, ClaudeAgentOptions, EDIT_TOOLS

    async def main():
        client = ClaudeClient()

        # One-shot query
        async for message in client.aquery("Fix bugs in main.py"):
            print(message)

        # Multi-turn conversation
        async with client.asession() as session:
            await session.asend("What files are in this project?")
            async for msg in session.areceive():
                print(msg)
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Optional
from contextlib import asynccontextmanager

try:
    from claude_agent_sdk import (
        query as sdk_query,
        ClaudeSDKClient,
        ClaudeAgentOptions as SDKOptions,
        AssistantMessage,
        ResultMessage,
        TextBlock,
        ToolUseBlock,
    )
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False


class PermissionMode(str, Enum):
    """Permission modes for tool execution."""
    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    BYPASS = "bypassPermissions"


# Predefined tool sets for common use cases
ANALYSIS_TOOLS = ["Read", "Glob", "Grep"]
EDIT_TOOLS = ["Read", "Edit", "Write", "Glob", "Grep"]
FULL_TOOLS = ["Read", "Edit", "Write", "Bash", "Glob", "Grep", "WebSearch", "WebFetch"]


@dataclass
class ClaudeAgentOptions:
    """Configuration options for Claude agent queries."""

    allowed_tools: list[str] = field(default_factory=lambda: EDIT_TOOLS)
    permission_mode: PermissionMode = PermissionMode.ACCEPT_EDITS
    max_turns: Optional[int] = None
    system_prompt: Optional[str] = None
    mcp_servers: Optional[dict[str, Any]] = None
    working_directory: Optional[str] = None

    def to_sdk_options(self) -> "SDKOptions":
        """Convert to SDK options format."""
        if not SDK_AVAILABLE:
            raise RuntimeError("claude-agent-sdk is not installed")

        return SDKOptions(
            allowed_tools=self.allowed_tools,
            permission_mode=self.permission_mode.value,
            max_turns=self.max_turns,
            system_prompt=self.system_prompt,
            mcp_servers=self.mcp_servers,
            cwd=self.working_directory,
        )


@dataclass
class AgentMessage:
    """Simplified message from agent execution."""

    type: str  # "text", "tool_use", "tool_result", "result"
    content: str
    tool_name: Optional[str] = None
    raw: Any = None

    @classmethod
    def from_sdk_message(cls, message: Any) -> Optional["AgentMessage"]:
        """Create AgentMessage from SDK message."""
        if not SDK_AVAILABLE:
            return None

        if isinstance(message, AssistantMessage):
            texts = []
            for block in message.content:
                if isinstance(block, TextBlock):
                    texts.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    return cls(
                        type="tool_use",
                        content=str(block.input),
                        tool_name=block.name,
                        raw=message
                    )
            if texts:
                return cls(type="text", content="\n".join(texts), raw=message)

        elif isinstance(message, ResultMessage):
            return cls(
                type="result",
                content=message.subtype,
                raw=message
            )

        return None


class ClaudeSession:
    """Multi-turn conversation session with Claude."""

    def __init__(self, client: "ClaudeSDKClient", options: ClaudeAgentOptions):
        self._client = client
        self._options = options

    async def asend(self, prompt: str) -> None:
        """Send a message to the session."""
        await self._client.query(prompt)

    async def areceive(self) -> AsyncIterator[AgentMessage]:
        """Receive and iterate over response messages."""
        async for message in self._client.receive_response():
            agent_msg = AgentMessage.from_sdk_message(message)
            if agent_msg:
                yield agent_msg

    async def aquery(self, prompt: str) -> AsyncIterator[AgentMessage]:
        """Send a message and receive responses in one call."""
        await self.asend(prompt)
        async for msg in self.areceive():
            yield msg


class ClaudeClient:
    """
    Claude Code SDK Client.

    Provides simplified access to Claude's agentic capabilities including:
    - One-shot queries with tool execution
    - Multi-turn conversation sessions
    - Configurable permissions and tool access

    Examples:
        # Simple one-shot query
        client = ClaudeClient()
        async for msg in client.aquery("Analyze main.py for bugs"):
            print(msg.content)

        # Query with custom options
        options = ClaudeAgentOptions(
            allowed_tools=ANALYSIS_TOOLS,
            permission_mode=PermissionMode.DEFAULT
        )
        async for msg in client.aquery("Review the codebase", options):
            print(msg.content)

        # Multi-turn conversation
        async with client.asession() as session:
            async for msg in session.aquery("What files exist?"):
                print(msg.content)
            async for msg in session.aquery("Show me the largest one"):
                print(msg.content)
    """

    def __init__(self, default_options: Optional[ClaudeAgentOptions] = None):
        """
        Initialize the Claude client.

        Args:
            default_options: Default options to use for all queries.
        """
        if not SDK_AVAILABLE:
            raise RuntimeError(
                "claude-agent-sdk is not installed. "
                "Install with: pip install claude-agent-sdk"
            )

        self._default_options = default_options or ClaudeAgentOptions()

    async def aquery(
        self,
        prompt: str,
        options: Optional[ClaudeAgentOptions] = None
    ) -> AsyncIterator[AgentMessage]:
        """
        Execute a one-shot query with Claude.

        Args:
            prompt: The task or question for Claude.
            options: Optional configuration overrides.

        Yields:
            AgentMessage objects as Claude processes the request.

        Example:
            async for msg in client.aquery("Fix type errors in utils.py"):
                if msg.type == "text":
                    print(msg.content)
                elif msg.type == "tool_use":
                    print(f"Using tool: {msg.tool_name}")
        """
        opts = options or self._default_options

        async for message in sdk_query(
            prompt=prompt,
            options=opts.to_sdk_options()
        ):
            agent_msg = AgentMessage.from_sdk_message(message)
            if agent_msg:
                yield agent_msg

    async def aquery_simple(
        self,
        prompt: str,
        options: Optional[ClaudeAgentOptions] = None
    ) -> str:
        """
        Execute a query and return only the final text response.

        Args:
            prompt: The task or question for Claude.
            options: Optional configuration overrides.

        Returns:
            Combined text output from Claude's response.

        Example:
            result = await client.aquery_simple("What's in README.md?")
            print(result)
        """
        texts = []
        async for msg in self.aquery(prompt, options):
            if msg.type == "text":
                texts.append(msg.content)
        return "\n".join(texts)

    @asynccontextmanager
    async def asession(
        self,
        options: Optional[ClaudeAgentOptions] = None
    ) -> AsyncIterator[ClaudeSession]:
        """
        Create a multi-turn conversation session.

        Args:
            options: Optional configuration for the session.

        Yields:
            ClaudeSession for multi-turn interactions.

        Example:
            async with client.asession() as session:
                async for msg in session.aquery("List Python files"):
                    print(msg.content)
                async for msg in session.aquery("Show the first one"):
                    print(msg.content)
        """
        opts = options or self._default_options

        async with ClaudeSDKClient() as sdk_client:
            yield ClaudeSession(sdk_client, opts)

    @staticmethod
    def check_sdk_available() -> bool:
        """Check if the Claude SDK is installed and available."""
        return SDK_AVAILABLE


async def amain_example():
    """Example usage of the ClaudeClient."""
    client = ClaudeClient()

    # One-shot query example
    print("=== One-shot Query ===")
    async for msg in client.aquery(
        "List the Python files in this directory",
        ClaudeAgentOptions(allowed_tools=ANALYSIS_TOOLS)
    ):
        if msg.type == "text":
            print(msg.content)
        elif msg.type == "tool_use":
            print(f"[Tool: {msg.tool_name}]")

    # Multi-turn session example
    print("\n=== Multi-turn Session ===")
    async with client.asession() as session:
        async for msg in session.aquery("What files are in the current directory?"):
            if msg.type == "text":
                print(msg.content)


if __name__ == "__main__":
    asyncio.run(amain_example())
