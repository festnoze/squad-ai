
import datetime
import random
import string
from langchain.tools import tool


from langchain.agents import AgentExecutor, create_tool_calling_agent, tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.language_models import BaseChatModel
from langchain import hub
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate
from langchain.schema.runnable import RunnableParallel

from helpers.agents_workflows import invoke_parallel_prompts
from helpers.txt_helper import txt
from models.param_doc import ParameterDocumentation, ParameterDocumentationPydantic
from models.params_doc import MethodParametersDocumentation

class ToolsHelper:
    @staticmethod
    def test_agent_executor_with_tools(llm):
        tools = [ToolsContainer.multiply, ToolsContainer.divide, ToolsContainer.add, ToolsContainer.subtract, ToolsContainer.power, ToolsContainer.root, ToolsContainer.get_random_string, ToolsContainer.get_random_number]
        question = "Take 3 to the fifth power and multiply that by the sum of twelve and three, then square root the whole result"
        answer = ToolsHelper.invoke_llm_with_tools(llm, tools, question)
        print(answer)

    @staticmethod
    def test_make_method_params_doc_with_agent_executor_and_tools(llm):
        tools = [ParameterDocumentation.create_parameter_documentation]
        question = "Here is the method 'divide' parameters: int dividand, int divisor. Please provide a description for each parameter."
        answer = ToolsHelper.invoke_llm_with_tools(llm, tools, question)
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

        print("Joke about bears:", txt.get_llm_answer_content(joke_result))
        print("Poem about trees:", txt.get_llm_answer_content(poem_result))
        print("Rebus about flowers:", txt.get_llm_answer_content(input_x_result))
        exit()
    def test_parallel_invocations_with_homemade_parallel_invocation(llm: BaseChatModel):        
        # Define different chains, assume both use {topic} in their templates
        prompts = [
            "Tell me a joke about flowers",
            "Write a short poem about darkness",
            "Write a short rebus about fruits"
        ]
        answers = invoke_parallel_prompts(llm, *prompts)
        for i, answer in enumerate(answers):
            print(f"Answer to prompt n°{i+1}: {txt.get_llm_answer_content(answer)}")
            print("--------------------------------------------------")
        exit()

    def test_parallel_invocations_no_template(llm: BaseChatModel):        
        # Define different chains, assume both use {topic} in their templates
        chain1 = ChatPromptTemplate.from_template("Tell me a joke about flowers") | llm
        chain2 = ChatPromptTemplate.from_template("Write a short poem about darkness") | llm
        chain3 = ChatPromptTemplate.from_template("Write a short rebus about fruits") | llm

        # Combine chains for parallel execution
        combined = RunnableParallel(joke=chain1, poem=chain2, xx=chain3)

        # Invoke the combined chain with specific inputs for each chain
        results = combined.invoke({"topic": ""})

        # Retrieve and print the output from each chain
        joke_result = results['joke']
        poem_result = results['poem']
        input_x_result = results['xx']

        print("Joke about flowers:", txt.get_llm_answer_content(joke_result))
        print("Poem about darkness:", txt.get_llm_answer_content(poem_result))
        print("Rebus about fruits:", txt.get_llm_answer_content(input_x_result))
        exit()

    @staticmethod
    def invoke_llm_with_tools(llm: BaseChatModel, tools: list[any], input: str) -> str:
        #prompt = hub.pull("hwchase17/openai-tools-agent")
        prompt = ChatPromptTemplate.from_messages(
                    [
                        ("system", "You're a helpful AI assistant. You know which tools use to solve the given user problem."),
                        ("human", "{input}"),
                        MessagesPlaceholder("agent_scratchpad")
                    ]
                )
        agent = create_tool_calling_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
        res = agent_executor.invoke({"input": input})
        return res["output"]

    @staticmethod
    def test_tool_bind(llm):
        """Test binding tools w/ direct binding to LLM - !! works only with few llm providers !! """
        tools = [ToolsContainer.multiply, ToolsContainer.divide, ToolsContainer.add, ToolsContainer.subtract, ToolsContainer.power, ToolsContainer.root]
        llm_with_tools = llm.bind_tools(tools)
        res = llm_with_tools.invoke("Calculate: 3 x 4")
        print(res)

class ToolsContainer:
    @tool
    def multiply(a: int, b: int) -> int:
        """Multiply two numbers."""
        return a * b

    @tool
    def divide(a: int, b: int) -> float:
        """Divide two numbers."""
        return a / b

    @tool
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @tool
    def subtract(a: int, b: int) -> int:
        """Subtract two numbers."""
        return a - b

    @tool
    def power(base: int, exponent: int) -> int:
        """Raise a number to a power."""
        return base ** exponent

    @tool
    def root(base: int, exponent: int) -> float:
        """Take the root of a number."""
        return base ** (1 / exponent)


    @tool
    def get_random_string(length: int) -> str:
        """Get a random string of a given length."""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

    @tool
    def get_random_number(length: int) -> str:
        """Get a random number of a given length."""
        return ''.join(random.choices(string.digits, k=length))

    @tool
    def get_random_email():
        """Get a random email address."""
        return ToolsContainer.get_random_string(10) + '@' + ToolsContainer.get_random_string(5) + '.com'

    @staticmethod
    def get_random_phone_number():
        return '0' + ToolsContainer.get_random_number(9)

    @staticmethod
    def get_random_date():
        return datetime.date(random.randint(1900, 2020), random.randint(1, 12), random.randint(1, 28))

    @staticmethod
    def get_random_datetime():
        return datetime.datetime(random.randint(1900, 2020), random.randint(1, 12), random.randint(1, 28),
                                 random.randint(0, 23), random.randint(0, 59), random.randint(0, 59))

    @staticmethod
    def get_random_time():
        return datetime.time(random.randint(0, 23), random.randint(0, 59), random.randint(0, 59))

    @staticmethod
    def get_random_boolean():
        return random.choice([True, False])

    @staticmethod
    def get_random_choice(choices):
        return random.choice(choices)

    @staticmethod
    def get_random_choices(choices, length):
        return random.choices(choices, k=length)

    @staticmethod
    def get_random_text(length):
        return ''.join(random.choices(string.ascii_uppercase + string.ascii_lowercase + string.digits + ' ', k=length))

    @staticmethod
    def get_random_paragraph(length):
        return ' '.join([ToolsContainer.get_random_text(random.randint(5, 15)) for _ in range(length)])

    @staticmethod
    def get_random_url():
        return 'http://' + ToolsContainer.get_random_string(10) + '.com'

    @staticmethod
    def get_random_image_url():
        return 'http://' + ToolsContainer.get_random_string(10) + '.com/image.png'

    @staticmethod
    def get_random_file_url():
        return 'http://' + ToolsContainer.get_random_string(10) + '.com/file.pdf'

    @staticmethod
    def get_random_video_url():
        return 'http://' + ToolsContainer.get_random