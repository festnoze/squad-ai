import unittest
import os
import sys
from unittest.mock import MagicMock

# Add the project root to the path so we can import the modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.dev_agent import DevAgent
from agents.unit_test_agent import UnitTestAgent
from agents.refactor_agent import RefactorAgent
from agents.analyst_agent import AnalystAgent

class TestPromptLoading(unittest.TestCase):
    def setUp(self):
        # Create a mock LLM for the agents
        self.mock_llm = MagicMock()
    
    def test_prompt_files_exist(self):
        """Test that all prompt files exist"""
        prompts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src", "prompts")
        
        # Check that the prompts directory exists
        self.assertTrue(os.path.exists(prompts_dir), "Prompts directory does not exist")
        
        # Check that each prompt file exists
        prompt_files = ["dev_prompt.txt", "test_prompt.txt", "refactor_prompt.txt", "analyst_prompt.txt"]
        for file_name in prompt_files:
            file_path = os.path.join(prompts_dir, file_name)
            self.assertTrue(os.path.exists(file_path), f"Prompt file {file_name} does not exist")
    
    def test_dev_agent_prompt_loading(self):
        """Test that the DevAgent can load its prompt"""
        agent = DevAgent(self.mock_llm)
        prompt = agent.load_dev_prompt()
        self.assertIsNotNone(prompt)
        self.assertGreater(len(prompt), 0)
    
    def test_test_agent_prompt_loading(self):
        """Test that the TestAgent can load its prompt"""
        agent = UnitTestAgent(self.mock_llm)
        prompt = agent.load_test_prompt()
        self.assertIsNotNone(prompt)
        self.assertGreater(len(prompt), 0)
    
    def test_refactor_agent_prompt_loading(self):
        """Test that the RefactorAgent can load its prompt"""
        agent = RefactorAgent(self.mock_llm)
        prompt = agent.load_refactor_prompt()
        self.assertIsNotNone(prompt)
        self.assertGreater(len(prompt), 0)
    
    def test_analyst_agent_prompt_loading(self):
        """Test that the AnalystAgent can load its prompt"""
        agent = AnalystAgent(self.mock_llm)
        prompt = agent.load_analyst_prompt()
        self.assertIsNotNone(prompt)
        self.assertGreater(len(prompt), 0)

if __name__ == "__main__":
    unittest.main()
