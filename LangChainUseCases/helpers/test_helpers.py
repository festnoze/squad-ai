from langchain.tools import tool
from langchain.agents import AgentExecutor, create_tool_calling_agent, tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate
from langchain.schema.runnable import RunnableParallel

from common_tools.helpers.tools_helpers import MathToolBox
from common_tools.helpers.llm_helper import Llm

def test_agent_executor_with_tools(llm):
    tools = [MathToolBox.multiply, MathToolBox.divide, MathToolBox.add, MathToolBox.subtract, MathToolBox.power, MathToolBox.root, MathToolBox.get_random_string, MathToolBox.get_random_number]
    question = "Take 3 to the fifth power and multiply that by the sum of twelve and three, then square root the whole result"
    answer = Llm.invoke_llm_with_tools(llm, tools, question)
    print(answer)

def test_parallel_invocations(llm: BaseChatModel):        
    # Define different chains, assume both use {topic} in their templates
    chain1 = ChatPromptTemplate.from_template("Tell me a joke about {topic}") | llm
    chain2 = ChatPromptTemplate.from_template("Write a short poem about {topic2}") | llm
    chain3 = ChatPromptTemplate.from_template("Write a short rebus about {input_x}") | llm

    # Combine chains for parallel execution
    combined = RunnableParallel(joke=chain1, poem=chain2, xx=chain3)

    # Invoke the combined chain with specific inputs for each chain
    results = combined.invoke({"topic": "bears", "topic2": "trees", "input_x": "flowers"})

    # Retrieve and print the output from each chain
    joke_result = results['joke']
    poem_result = results['poem']
    input_x_result = results['xx']

    print("Joke about bears:", Llm.get_llm_answer_content(joke_result))
    print("Poem about trees:", Llm.get_llm_answer_content(poem_result))
    print("Rebus about flowers:", Llm.get_llm_answer_content(input_x_result))
    exit()

def test_parallel_invocations_with_homemade_parallel_prompts_invocations(llm: BaseChatModel):        
    # Define different chains, assume both use {topic} in their templates
    prompts = [
        "Tell me a joke about flowers",
        "Write a short poem about darkness",
        "Write a short rebus about fruits"
    ]
    answers = Llm.invoke_parallel_prompts("test_homemade_parallel_invocation", llm, *prompts)
    for i, answer in enumerate(answers):
        print(f"Answer to prompt n°{i+1}: {Llm.get_llm_answer_content(answer)}")
        print("--------------------------------------------------")
    exit()

def test_parallel_invocations_with_homemade_parallel_chains_invocations(llm: BaseChatModel):
    prompts = [
        "Tell me a joke about flowers",
        "Write a short poem about darkness",
        "Write a short rebus about fruits"
    ]
    chains= []
    for prompt in prompts:
        chain = ChatPromptTemplate.from_template(prompt) | llm
        chains.append(chain)
    answers = Llm.invoke_parallel_chains(None, *chains)
    for i, answer in enumerate(answers):
        print(f"Answer to prompt n°{i+1}: {Llm.get_llm_answer_content(answer)}")
        print("--------------------------------------------------")
    exit()

def test_parallel_chains_invocations_with_imputs(llm: BaseChatModel):
    prompts = [
        "Tell me a joke about {input_1}",
        "Write a short poem about {input_2}",
        "Write a short rebus about {input_3}"
    ]
    chains= []
    for prompt in prompts:
        chain = ChatPromptTemplate.from_template(prompt) | llm
        chains.append(chain)
    inputs = {"input_1": "flowers", "input_2": "darkness", "input_3": "fruits"}
    answers = Llm.invoke_parallel_chains(inputs, *chains)
    for i, answer in enumerate(answers):
        print(f"Answer to prompt n°{i+1}: {Llm.get_llm_answer_content(answer)}")
        print("--------------------------------------------------")
    exit()

def test_parallel_invocations_no_template(llm: BaseChatModel):        
    # Define different chains, assume both use {input} in their templates
    chain1 = ChatPromptTemplate.from_template("Tell me a joke about flowers") | llm
    chain2 = ChatPromptTemplate.from_template("Write a short poem about darkness") | llm
    chain3 = ChatPromptTemplate.from_template("Write a short rebus about fruits") | llm

    # Combine chains for parallel execution
    combined = RunnableParallel(joke=chain1, poem=chain2, xx=chain3)

    # Invoke the combined chain with specific inputs for each chain
    results = combined.invoke({"input": ""})

    # Retrieve and print the output from each chain
    joke_result = results['joke']
    poem_result = results['poem']
    input_x_result = results['xx']

    print("Joke about flowers:", Llm.get_llm_answer_content(joke_result))
    print("Poem about darkness:", Llm.get_llm_answer_content(poem_result))
    print("Rebus about fruits:", Llm.get_llm_answer_content(input_x_result))
    exit()

def test_tool_bind(llm):
    """Test binding tools w/ direct binding to LLM - !! works only with few llm providers !! """
    tools = [MathToolBox.multiply, MathToolBox.divide, MathToolBox.add, MathToolBox.subtract, MathToolBox.power, MathToolBox.root]
    llm_with_tools = llm.bind_tools(tools)
    res = llm_with_tools.invoke("Calculate: 3 x 4")
    print(res)