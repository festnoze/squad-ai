from langchain_core.messages import HumanMessage
from langchain_community.llms import Ollama
from langchain_community.tools import DuckDuckGoSearchRun # search duck duck go API
from langchain_experimental.llms.ollama_functions import OllamaFunctions

from crewai_tools import SerperDevTool # search google API
from langchain_community.tools import DuckDuckGoSearchRun # search duck duck go API

agent = OllamaFunctions(model="nous-hermes2")
search_internet = SerperDevTool()

agent = agent.bind(
    functions=[
        {
            "name": "search_internet",
            "description": "search for information over the internet",
            "parameters": {
                "type": "string",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The string to search for",
                    },
                },
                "required": ["query"],
            },
        }
    ],
    function_call={"name": "search_internet"},
)


response = agent.invoke("what is the weather in Montpellier today?")
print(response)
