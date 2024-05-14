import datetime
import random
import string

from langchain.tools import tool
from langchain.agents import AgentExecutor, create_tool_calling_agent, tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

class ToolsHelper:
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