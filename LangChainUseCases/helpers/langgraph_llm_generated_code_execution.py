from langgraph.graph import Graph, StateGraph, END
from langchain_core.messages import SystemMessage
from langchain.tools import tool
from langchain_core.language_models import BaseChatModel
from langchain_core.agents import AgentFinish
from langgraph.prebuilt import ToolInvocation
from langchain_core.messages import FunctionMessage
from langgraph.prebuilt.tool_executor import ToolExecutor
from langchain.tools.render import format_tool_to_openai_function
from langchain.agents import Tool
from langchain_experimental.utilities import PythonREPL
#
from common_tools.helpers.file_helper import file
from common_tools.helpers.llm_helper import Llm
from common_tools.helpers.tools_helpers import MathToolBox, RandomToolBox, WordsToolBox
from common_tools.helpers.txt_helper import txt
from common_tools.models.langchain_adapter_type import LangChainAdapterType
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.models.langgraph_agent_state import AgentState
from common_tools.models.llm_info import LlmInfo

class LangGraphLlmGeneratedCodeExecution:
    def __init__(self, llm: BaseChatModel, tools: list) -> None:
        self.llm = llm
        
        # Execute arbitrary python code tool
        python_repl = PythonREPL()
        repl_tool = Tool(
            name="python_repl",
            description="A Python shell. Use this to execute python commands. Input should be a valid python command. If you want to see the output of a value, you should print it out with `print(...)`.",
            func=python_repl.run,
        )

        # Pass the tool to the agent supervisor & to the tool executor
        all_tools = [repl_tool]
        
        additionnal_tools = [format_tool_to_openai_function(t) for t in tools] #TODO: check compatibility out of OpenAI
        all_tools.extend(additionnal_tools)
        self.llm = self.llm.bind_functions(all_tools)
        self.tool_executor = ToolExecutor(all_tools)
        WordsToolBox.llm_or_chain = self.llm

    # Define the function that calls the model
    def llm_agent_code_generator(self, state):
        # Initialize the AgentState with the instructions
        codeact_instructions = file.get_as_str("llm_generated_code_execution_instructions.txt")
        instructions_message = SystemMessage(content=codeact_instructions)
        messages=[instructions_message]
        messages.extend(state['messages'])
        
        response = self.llm.invoke(messages)
        # We return a list, because this will get added to the existing list
        return {"messages": [Llm.get_code_block("python", response)]}

    # Define the function to execute tools
    def call_tool(self, state):     
        messages = state['messages']   
        # Based on the continue condition
        # we know the last message involves a function call
        last_message = messages[-1]
        # We construct an ToolInvocation from the function_call
        action = ToolInvocation(
            tool=last_message.additional_kwargs["function_call"]["name"],
            tool_input=last_message.additional_kwargs["function_call"]["arguments"],
        )
        print(f"The agent action is {action}")
        response = self.tool_executor.invoke(action)
        print(f"The tool result is: {response}")
        function_message = FunctionMessage(content=str(response), name=action.tool)
        return {"messages": [function_message]}
    
    def should_continue(self, state):
        messages = state['messages']
        last_message = messages[-1]
        
        if "function_call" not in last_message.additional_kwargs: # If there is no function call, then we finish
            return "end"
        else:
            return "continue"

    def build_graph(self):
        # Initialize the StateGraph
        workflow = StateGraph(AgentState)

        workflow.add_node("agent", self.llm_agent_code_generator)
        workflow.add_node("action", self.call_tool)

        workflow.set_entry_point("agent")

        workflow.add_conditional_edges(
            # First, we define the start node. We use `agent`.
            # This means these are the edges taken after the `agent` node is called.
            "agent",
            # Next, we pass in the function that will determine which node is called next.
            self.should_continue,
            # Finally we pass in a mapping.
            # The keys are strings, and the values are other nodes.
            # END is a special node marking that the graph should finish.
            # What will happen is we will call `should_continue`, and then the output of that
            # will be matched against the keys in this mapping.
            # Based on which one it matches, that node will then be called.
            {
                # If `tools`, then we call the tool node.
                "continue": "action",
                # Otherwise we finish.
                "end": END
            }
        )

        # We now add a normal edge from `tools` to `agent`.
        # This means that after `tools` is called, `agent` node is called next.
        workflow.add_edge('action', 'agent')
        wf = workflow.compile()

        return wf
