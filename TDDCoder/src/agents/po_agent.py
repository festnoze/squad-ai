import logging
from langchain.tools import tool
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel, Field

# Pydantic models for tool arguments for robust validation
class ExtractRequirementsArgs(BaseModel):
    user_input: str = Field(description="The user's input to extract requirements from")

class CreateUserStoryArgs(BaseModel):
    requirements: dict[str, str] = Field(description="A dictionary of requirements including user_type, action, and benefit")

class POAgent:
    def __init__(self, llm):
        self.logger = logging.getLogger(__name__)
        self.llm = llm
        
        self.tools = [
            self.extract_requirements,
            self.create_user_story
        ]
        
        prompt = self._load_prompt()
        prompts = ChatPromptTemplate.from_messages([
            ("system", prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{user_request}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        agent = create_tool_calling_agent(self.llm, self.tools, prompts)
        self.agent_executor = AgentExecutor(
            agent=agent, 
            tools=self.tools, 
            verbose=True, 
            return_intermediate_steps=True
        )
    
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
    
    @tool(args_schema=ExtractRequirementsArgs)
    def extract_requirements(self, user_input: str) -> dict[str, str]:
        """Extract key requirements from the user's input"""
        return {
            "user_type": "user",
            "action": "perform an action",
            "benefit": "achieve a goal",
            "technical_constraints": []
        }
    
    @tool(args_schema=CreateUserStoryArgs)
    def create_user_story(self, requirements: dict[str, str]) -> dict[str, str]:
        """Create a formal User Story from the extracted requirements"""
        return {
            "title": "Implement feature X",
            "narrative": f"As a {requirements.get('user_type', 'user')}, I want to {requirements.get('action', 'do something')} so that {requirements.get('benefit', 'achieve something')}",
            "acceptance_criteria": ["Criteria 1", "Criteria 2"],
            "technical_notes": requirements.get("technical_constraints", []),
            "priority": "Medium"
        }
    
    def run(self, state):
        """Run the PO Agent to create a User Story"""
        try:
            user_request = state.user_request
            chat_history = state.chat_history
            
            result = self.agent_executor.invoke({
                "user_request": user_request,
                "chat_history": chat_history
            })

            # Find the user story from the tool calls in intermediate steps
            user_story = {}
            if 'intermediate_steps' in result:
                for action, tool_output in result['intermediate_steps']:
                    if action.tool == 'create_user_story':
                        user_story = tool_output
                        break
            
            state.user_story = user_story
            state.current_agent = "qa_agent"
            state.chat_history.append({"role": "assistant", "content": result.get("output", "")})
            
            return state
        except Exception as e:
            self.logger.error(f"Error in PO Agent: {e}", exc_info=True)
            state.error = True
            state.error_message = f"Error in PO Agent: {e}"
            return state
