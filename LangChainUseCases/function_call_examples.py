from common_tools.helpers.llm_helper import Llm
from common_tools.helpers.tools_helpers import MathToolBox, RandomToolBox, WordsToolBox
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.models.langgraph_agent_state import AgentState
#
from helpers.langgraph_llm_generated_code_execution import LangGraphLlmGeneratedCodeExecution
from helpers.langgraph_tools_supervisor import LangGraphToolsSupervisor

class FunctionCallExamples:

    # Complex prompt with multiple sub-parts, needed reflexion and tools
    prompt = """get a random number, add 7 to it, divide the result be three, round it to the nearest integer, 
    convert this number in french word, then integrate this french word into a leet sentence
    speaking of giving a defined quantity of flowers to a beloved one. The number of flowers is the previous number in french word. output the sentence in lower snake case."""
    
    prompt_single_tool = """get a random number."""
        
    tools = [
        WordsToolBox.to_lowercase, RandomToolBox.get_random_number, WordsToolBox.number_to_french_words, 
        WordsToolBox.text_to_leet, WordsToolBox.to_upper_snake_case, WordsToolBox.translate_in_spanish, 
        MathToolBox.add, MathToolBox.divide, MathToolBox.round_int
    ] 

    @staticmethod
    def resolve_using_direct_llm_wo_tools(llms_infos):
        llm = LangChainFactory.create_llms_from_infos(llms_infos)[0]
        print('👁 Direct LLM resolution:')
        print(FunctionCallExamples.prompt)
        result = llm.invoke(FunctionCallExamples.prompt) 
        print(Llm.get_content(result))
        print('-----------------------------------')
        exit()

    @staticmethod
    async def resolve_using_agent_executor_tool_call_async(llms_infos):
        llm = LangChainFactory.create_llms_from_infos(llms_infos)[0]
        print('👁 LLM resolution with AgentExecutor and tools:') 
        print(FunctionCallExamples.prompt)
        WordsToolBox.llm_or_chain = llm # set the llm to be used by the tools
        result = await Llm.invoke_agent_executor_with_tools_async(llm, FunctionCallExamples.tools, FunctionCallExamples.prompt)    
        print(Llm.get_content(result))
        print('-----------------------------------')
        exit()

    
    @staticmethod
    async def resolve_using_native_single_tool_call_async(llms_infos):
        llm = LangChainFactory.create_llms_from_infos(llms_infos)[0]
        print('👁 LLM resolution with single native tool:') 
        print(FunctionCallExamples.prompt)
        WordsToolBox.llm_or_chain = llm # set the llm to be used by the tools
        result = await Llm.invoke_llm_with_tool_async(llm, FunctionCallExamples.tools, FunctionCallExamples.prompt_single_tool)    
        print(Llm.get_content(result))
        print('-----------------------------------')
        exit()

    @staticmethod
    def resolve_using_agent_with_manual_tool_call_in_graph(llms_infos):
        llm = LangChainFactory.create_llms_from_infos(llms_infos)[0]
        print('👁 Resolution using Agent and tools (w/ graph):') 
        print(FunctionCallExamples.prompt) 
        graph_test = LangGraphToolsSupervisor(llm, FunctionCallExamples.tools)
        graph = graph_test.build_graph()
        agentState: AgentState = graph.invoke({"messages": [FunctionCallExamples.prompt]})
        print(Llm.get_content(agentState['messages'][-1]))
        print('-----------------------------------')
        exit()

    @staticmethod
    def resolve_using_langchain_tool_call(llms_infos):
        llm = LangChainFactory.create_llms_from_infos(llms_infos)[0]
        print('👁 Resolution using LangChain tool call:') 
        print(FunctionCallExamples.prompt)
        WordsToolBox.llm_or_chain = llm
        result = WordsToolBox.integrate_into_leet_sentence(WordsToolBox.round_int(MathToolBox.divide(MathToolBox.add(RandomToolBox.get_random_number(), 7), 3)))
        print(result)
        print('-----------------------------------')
        exit()
        
    @staticmethod
    def resolve_using_codeact_code_execution(llms_infos):
        llm = LangChainFactory.create_llms_from_infos(llms_infos)[0]
        print('👁 Resolution using LLM-generated code execution (CodeAct w/ graph):')  
        print(FunctionCallExamples.prompt)
        graph_code_execution = LangGraphLlmGeneratedCodeExecution(llm, [])
        graph = graph_code_execution.build_graph()
        agentState: AgentState = graph.invoke({"messages": [FunctionCallExamples.prompt]})
        print(Llm.get_content(agentState['messages'][-1]))
        print('-----------------------------------')
        exit()