from typing import Dict, List, Any, Optional
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

class ConceptionWorkflowState(BaseModel):
    """State for the Conception Workflow."""
    # Input
    user_request: str = Field(default="", description="The original user request")
    
    # Artifacts
    requirements: Dict[str, Any] = Field(
        default_factory=dict,
        description="Requirements extracted from the user request"
    )
    user_story: Dict[str, Any] = Field(
        default_factory=dict,
        description="User story created from the requirements"
    )
    scenarios: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Gherkin/BDD scenarios created from the user story"
    )
    
    # Control flow
    error: bool = Field(default=False, description="Flag indicating if an error occurred")
    error_message: str = Field(default="", description="Error message if an error occurred")
    
    # Conversation history
    conversation_history: List[BaseMessage] = Field(
        default_factory=list,
        description="History of the conversation"
    )
