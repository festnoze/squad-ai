from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

class TDDWorkflowState(BaseModel):
    """State for the TDD Implementation Workflow."""
    user_request: str = Field(default="", description="The original user request from the user")
    # Input from conception workflow
    user_story: dict[str, str] = Field(
        default_factory=dict,
        description="User story from the conception workflow"
    )
    scenarios: list[dict[str, str]] = Field(
        default_factory=list,
        description="Gherkin/BDD scenarios from the conception workflow"
    )
    
    # Analyst artifacts
    implementation_steps: list[dict[str, str]] = Field(
        default_factory=list,
        description="Steps identified by the analyst for implementation"
    )
    current_step_index: int = Field(
        default=0,
        description="Index of the current implementation step"
    )
    is_implementation_complete: bool = Field(
        default=False,
        description="Flag indicating if all implementation steps are complete"
    )
    chat_history: list[dict[str, str]] = Field(
        default_factory=list,
        description="History of the conversation"
    )
    
    # Implementation artifacts
    remaining_scenarios: list[dict[str, str]] = Field(
        default_factory=list,
        description="Scenarios that still need to be implemented"
    )
    current_scenario: dict[str, str] = Field(
        default_factory=dict,
        description="The current scenario being implemented"
    )
    tests: str = Field(default="", description="Unit tests for the current scenario")
    code: str = Field(default="", description="Implementation code for the current scenario")
    refactored_code: str = Field(default="", description="Refactored code for the current scenario")
    tests_passed: bool = Field(default=False, description="Flag indicating if the tests pass")
    
    # Control flow
    error: bool = Field(default=False, description="Flag indicating if an error occurred")
    error_message: str = Field(default="", description="Error message if an error occurred")
    
    # Conversation history
    conversation_history: list[BaseMessage] = Field(
        default_factory=list,
        description="History of the conversation"
    )
