from langgraph.graph import Graph, StateGraph, END
from langchain.tools import tool
from langchain_core.language_models import BaseChatModel
from langchain_core.agents import AgentFinish
from langgraph.prebuilt import ToolInvocation
import json
from langchain_core.messages import FunctionMessage
from langgraph.prebuilt.tool_executor import ToolExecutor
from langchain.tools.render import format_tool_to_openai_function
#
from common_tools.helpers.llm_helper import Llm
from common_tools.helpers.tools_helpers import MathToolBox, RandomToolBox, WordsToolBox
from common_tools.helpers.txt_helper import txt
from common_tools.langchains.langchain_adapter_type import LangChainAdapterType
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.langchains.langgraph_agent_state import AgentState
from common_tools.models.llm_info import LlmInfo

class LangGraphToolsSupervisor:
    def __init__(self, llm: BaseChatModel, tools: list) -> None:
        self.llm = llm
        self.tool_executor = ToolExecutor(tools)
        functions = [format_tool_to_openai_function(t) for t in tools]
        self.llm = self.llm.bind_functions(functions)
        WordsToolBox.llm = self.llm

    # Define the function that calls the model
    def call_model(self, state):
        messages = state['messages']
        response = self.llm.invoke(messages)
        # We return a list, because this will get added to the existing list
        return {"messages": [response]}

    # Define the function to execute tools
    def call_tool(self, state):
        messages = state['messages']
        # Based on the continue condition
        # we know the last message involves a function call
        
        last_message = messages[-1]
        # We construct an ToolInvocation from the function_call
        action = ToolInvocation(
            tool=last_message.additional_kwargs["function_call"]["name"],
            tool_input=json.loads(last_message.additional_kwargs["function_call"]["arguments"]),
        )
        print(f"The agent action is {action}")
        response = self.tool_executor.invoke(action)
        print(f"The tool result is: {response}")
        function_message = FunctionMessage(content=str(response), name=action.tool)
        return {"messages": [function_message]}
    
    def should_continue(self, state):
        messages = state['messages']
        last_message = messages[-1]
        
        # If there is no function call, then we finish
        if last_message.additional_kwargs and "function_call" in last_message.additional_kwargs: 
            return "continue"
        else:
            return "end"

    def build_graph(self):
        workflow = StateGraph(AgentState)

        workflow.add_node("agent", self.call_model)
        workflow.add_node("action", self.call_tool)

        workflow.set_entry_point("agent")
        #workflow.set_finish_point("action")
        
        #workflow.add_edge('agent', 'action')
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
