import yaml
import os
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())
from env import env
env.api_key = os.getenv("OPEN_API_KEY")
#from langchain.llms.openai import OpenAI, OpenAIChat
from langchain_community.llms import Ollama
from crewai import Crew, Agent, Task, Process
from crewai_tools import SerperDevTool # search google API
from langchain_community.tools import DuckDuckGoSearchRun # search duck duck go API

def get_config_file(base_name):
    # List of possible file extensions and suffixes
    extensions = ['.yaml', '.yml']
    suffixes = ['', '_config']

    # Generate a list of potential filenames
    potential_files = [base_name + suffix + ext for ext in extensions for suffix in suffixes]

    # Check if any of the potential files exist
    
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    for filename in potential_files:
        if os.path.exists(filename):
            with open(filename, 'r') as file:
                config = yaml.safe_load(file)
            return config
        
    print(f"Error: No config file found for '{base_file_name}'.")
    exit()

base_file_name = os.path.splitext(os.path.basename(__file__))[0]
config = get_config_file(base_file_name)
llm = Ollama(model="nous-hermes2")

# set used tools first
search_tool = SerperDevTool()
    
# Initialize agents and tasks based on the YAML file
agents = []
agents_dict = {}  # Keep track of agents by their role
for agent_config in config['crew']['agents']:
    agent_tools_names = agent_config.pop('tools', [])
    agent_tools = [globals()[name] for name in agent_tools_names]  # Create tools instances by name
    agent = Agent(**agent_config, llm=llm)
    agent.tools = agent_tools
    agents.append(agent)
    agents_dict[agent.role] = agent  # Store the agent instance by role

# Initialize tasks with references to the actual agent instances
tasks = []
for task_config in config['crew']['tasks']:
    # Replace the 'agent' string with the actual Agent object from agents_dict
    agent_role = task_config.pop('agent')
    agent = agents_dict.get(agent_role)
    if agent:
        task = Task(**task_config, agent=agent)
        tasks.append(task)
    else:
        print(f"Error: No agent with the role '{agent_role}' found for the task.")

# Initialize the crew with the loaded configuration
crew = Crew(
    agents=agents,
    tasks=tasks,
    process= Process(config['crew']['process']),
    verbose=config['crew']['verbose'])

# Execute the crew
result = crew.kickoff()
print(result)
