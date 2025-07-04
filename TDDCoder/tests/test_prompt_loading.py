import pytest
import os
from unittest.mock import MagicMock

from agents.dev_agent import DevAgent
from agents.unit_test_agent import UnitTestAgent
from agents.refactor_agent import RefactorAgent
from agents.analyst_agent import AnalystAgent

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src", "prompts")
PROMPT_FILES = [
    "dev_prompt.txt",
    "test_prompt.txt",
    "refactor_prompt.txt",
    "analyst_prompt.txt"
]

AGENT_CLASSES_AND_METHODS = [
    (DevAgent, "load_dev_prompt"),
    (UnitTestAgent, "load_test_prompt"),
    (RefactorAgent, "load_refactor_prompt"),
    (AnalystAgent, "load_analyst_prompt"),
]

@pytest.fixture
def mock_llm():
    """Create a mock LLM for testing."""
    return MagicMock()


@pytest.mark.parametrize("file_name", PROMPT_FILES)
def test_prompt_file_exists(file_name: str):
    """Test that all prompt files exist."""
    # Check that the prompts directory exists
    assert os.path.exists(PROMPTS_DIR), "Prompts directory does not exist"

    # Check that each prompt file exists
    file_path = os.path.join(PROMPTS_DIR, file_name)
    assert os.path.exists(file_path), f"Prompt file {file_name} does not exist"


@pytest.mark.parametrize("agent_class, load_method_name", AGENT_CLASSES_AND_METHODS)
def test_agent_prompt_loading(agent_class, load_method_name: str, mock_llm):
    """Test that each agent can load its prompt."""
    agent = agent_class(mock_llm)
    load_method = getattr(agent, load_method_name)
    prompt = load_method()

    assert prompt is not None
    assert len(prompt) > 0
