import yaml
import os
from env import env
from dotenv import load_dotenv
load_dotenv()
# openai_api_key = os.getenv("OPEN_API_KEY")
# env.api_key = openai_api_key
from langchain_community.llms import Ollama
from crewai import Crew, Agent, Process, Task
from crewai_tools import SerperDevTool

# create LLM instance
llm = Ollama(model="nous-hermes2")

def get_config_file(base_name):
    # List of possible file extensions and suffixes
    extensions = ['.yaml', '.yml']
    suffixes = ['', '_config']

    # Generate a list of potential filenames
    potential_files = [base_name + suffix + ext for ext in extensions for suffix in suffixes]

    # Check if any of the potential files exist
    for filename in potential_files:
        if os.path.exists(filename):
            with open(filename, 'r') as file:
                config = yaml.safe_load(file)
            return config
        
    print(f"Error: No config file found for '{base_file_name}'.")
    exit()

# Use the function to get the config file
base_file_name = os.path.splitext(os.path.basename(__file__))[0]
config = get_config_file(base_file_name)

# load tools first
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
