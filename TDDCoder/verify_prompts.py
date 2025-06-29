from src.agents.dev_agent import DevAgent
from src.agents.unit_test_agent import UnitTestAgent
from src.agents.refactor_agent import RefactorAgent
from src.agents.analyst_agent import AnalystAgent
from unittest.mock import MagicMock

# Create a mock LLM
llm = MagicMock()

# Initialize agents
dev_agent = DevAgent(llm)
test_agent = UnitTestAgent(llm)
refactor_agent = RefactorAgent(llm)
analyst_agent = AnalystAgent(llm)

# Test prompt loading
print('DevAgent prompt loaded:', dev_agent.load_dev_prompt()[:100] + '...')
print('TestAgent prompt loaded:', test_agent.load_test_prompt()[:100] + '...')
print('RefactorAgent prompt loaded:', refactor_agent.load_refactor_prompt()[:100] + '...')
print('AnalystAgent prompt loaded:', analyst_agent.load_analyst_prompt()[:100] + '...')
