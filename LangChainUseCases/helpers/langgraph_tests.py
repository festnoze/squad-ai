import os
import random

from langgraph.graph import Graph
from langchain.tools import tool
from helpers.llm_helper import Llm
from helpers.tools_helpers import MathToolBox, RandomToolBox, WordsToolBox
from helpers.txt_helper import txt
from langchains.langchain_adapter_type import LangChainAdapterType
from langchains.langchain_factory import LangChainFactory
from langchains.langgraph_agent_state import AgentState
from langchain_core.language_models import BaseChatModel

class LangGraphTest1:
    llm: BaseChatModel = None    
    def node1(query_str):
        return query_str

    def node2(query_str):
        tools = [WordsToolBox.to_lowercase, RandomToolBox.get_random_number, WordsToolBox.number_to_french_words, WordsToolBox.text_to_leet, WordsToolBox.to_upper_snake_case, WordsToolBox.translate_in_spanish, MathToolBox.add, MathToolBox.divide, MathToolBox.round_int]
        WordsToolBox.llm = LangGraphTest1.llm # set the llm to be used by the tools
        
        answer = Llm.invoke_llm_with_tools(LangGraphTest1.llm, tools, query_str)
        return answer
        

    def get_graph_1():
        workflow = Graph()

        workflow.add_node("node_1", LangGraphTest1.node1)
        workflow.add_node("node_2", LangGraphTest1.node2)

        workflow.add_edge('node_1', 'node_2')

        workflow.set_entry_point("node_1")
        workflow.set_finish_point("node_2")

        wf = workflow.compile()
        return wf
