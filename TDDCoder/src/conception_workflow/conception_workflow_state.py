from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field
from typing import Any

class ConceptionWorkflowState(BaseModel):
    """State for the Conception Workflow."""
    # Input
    user_request: str = Field(default="", description="The original user request")
    
    # Artifacts
    requirements: dict[str, Any] = Field(
        default_factory=dict,
        description="Requirements extracted from the user request"
    )
    user_story: dict[str, Any] = Field(
        default_factory=dict,
        description="User story created from the requirements"
    )
    scenarios: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Gherkin/BDD scenarios created from the user story"
    )
    
    # Control flow
    error: bool = Field(default=False, description="Flag indicating if an error occurred")
    error_message: str = Field(default="", description="Error message if an error occurred")
    
    # Conversation history
    conversation_history: list[BaseMessage] = Field(
        default_factory=list,
        description="History of the conversation"
    )
