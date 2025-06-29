import logging
from langchain.tools import tool
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

class POAgent:
    def __init__(self, llm):
        self.logger = logging.getLogger(__name__)
        self.llm = llm
        
        # Define tools
        self.tools = [
            self.extract_requirements,
            self.create_user_story
        ]
        
        # Create prompt
        prompt = self._load_prompt()
        prompts = ChatPromptTemplate.from_messages([
            ("system", prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{user_request}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        # Create agent
        agent = create_tool_calling_agent(self.llm, self.tools, prompts)
        self.agent_executor = AgentExecutor(agent=agent, tools=self.tools, verbose=True)
    
    def _load_prompt(self) -> str:
        return """You are a Product Owner agent responsible for understanding user requirements and creating a formal User Story.
        
Your task is to have a conversation with the user to understand their requirements, and then create a well-structured User Story.

A good User Story follows the format:
As a [type of user], I want [an action] so that [a benefit/value].

Additionally, you should include:
- Acceptance Criteria: Clear conditions that must be met for the story to be considered complete
- Technical Notes: any technical considerations or constraints
- Dependencies: any dependencies on other features or systems
- Priority: The importance of this story (High, Medium, Low)

Use the provided tools to extract requirements and create the User Story.
"""
    
    @tool
    def extract_requirements(self, user_input: str) -> dict[str, any]:
        """Extract key requirements from the user's input"""
        # Implementation would use the LLM to extract requirements
        # For now, we'll return a placeholder
        return {
            "user_type": "user",
            "action": "perform an action",
            "benefit": "achieve a goal",
            "technical_constraints": []
        }
    
    @tool
    def create_user_story(self, requirements: dict[str, any]) -> dict[str, any]:
        """Create a formal User Story from the extracted requirements"""
        # Implementation would use the LLM to create a user story
        # For now, we'll return a placeholder
        return {
            "title": "Implement feature X",
            "narrative": f"As a {requirements['user_type']}, I want to {requirements['action']} so that {requirements['benefit']}",
            "acceptance_criteria": [
                "Criteria 1: The system should...",
                "Criteria 2: When the user...",
            ],
            "technical_notes": requirements.get("technical_constraints", []),
            "priority": "Medium"
        }
    
    def run(self, state):
        """Run the PO Agent to create a User Story"""
        try:
            # Extract the user request from the state
            user_request = state.user_request
            chat_history = state.chat_history
            
            # Invoke the agent
            result = self.agent_executor.invoke({
                "user_request": user_request,
                "chat_history": chat_history
            })
            
            # Update the state with the user story
            state.user_story = result.get("user_story", {})
            state.chat_history.append({"role": "assistant", "content": result.get("output", "")})
            state.current_agent = "qa_agent"  # Move to the next agent
            
            return state
        except Exception as e:
            self.logger.error(f"Error in PO Agent: {str(e)}")
            state.error_message = f"Error in PO Agent: {str(e)}"
            return state
