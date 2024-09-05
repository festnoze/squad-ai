import os
from dotenv import find_dotenv, load_dotenv
from env import env

load_dotenv(find_dotenv())
env.api_key = os.getenv("OPEN_API_KEY")
env.serper_api_key = os.getenv("SERPER_API_KEY")

from crewai import Agent, Task, Crew, Process
from crewai_tools import SerperDevTool

# Assuming the availability of a tool to help with software development tasks.
development_tool = SerperDevTool()

# Senior Software Engineer Agent
senior_software_engineer = Agent(
    role='Senior Software Engineer',
    goal='Architect and develop the backend of the Flood-It game using C# .NET',
    verbose=True,
    memory=True,
    backstory=(
        "As a Senior Software Engineer with extensive experience in the .NET ecosystem, "
        "you're tasked with creating a robust, scalable backend for the Flood-It game. "
        "Your expertise in software architecture and efficient algorithms are crucial for the project."
    ),
    tools=[development_tool],
    allow_delegation=False
)

# Blazor Frontend Developer Agent
blazor_frontend_developer = Agent(
    role='Blazor Frontend Developer',
    goal='Develop the frontend of the Flood-It game using Blazor',
    verbose=True,
    memory=True,
    backstory=(
        "Specializing in Blazor, you are responsible for crafting an engaging user interface for the Flood-It game. "
        "Your role is to integrate seamlessly with the backend services and ensure a responsive experience across devices."
    ),
    tools=[development_tool],
    allow_delegation=False
)

# Software Quality Control Engineer Agent
quality_control_engineer = Agent(
    role='Software Quality Control Engineer',
    goal='Identify and fix bugs in the game code',
    verbose=True,
    memory=True,
    backstory=(
        "With a keen eye for detail, your task is to analyze both backend and frontend code for the Flood-It game, "
        "identifying and rectifying any bugs, glitches, or inefficiencies."
    ),
    tools=[development_tool],
    allow_delegation=False
)

# Chief Software Quality Control Engineer Agent
chief_quality_control_engineer = Agent(
    role='Chief Software Quality Control Engineer',
    goal='Ensure the game meets all functional requirements and is ready for release',
    verbose=True,
    memory=True,
    backstory=(
        "Overseeing the quality assurance process, you are dedicated to ensuring the Flood-It game is of the highest quality, "
        "covering unit tests, integration tests, and user acceptance testing."
    ),
    tools=[development_tool],
    allow_delegation=True
)

# Game Design Task
game_design_task = Task(
    description="Define the game's concept, rules, and mechanics.",
    expected_output='A detailed game design document outlining the Flood-It game.',
    tools=[development_tool],
    agent=senior_software_engineer,  # Assigning to the senior software engineer for initial concept
)

def save_task_output(content, directory, filename):
    """
    Saves task output to a file in the specified directory.
    
    Args:
    output (str): The output to save.
    directory (str): The directory where the file will be saved.
    filename (str): The name of the file.
    """
    os.makedirs(directory, exist_ok=True)  # Ensure the directory exists
    filepath = os.path.join(directory, filename)
    with open(filepath, 'w') as file:
        file.write(content)
    print(f"Output saved to {filepath}")


# Quality Assurance Task
quality_assurance_task = Task(
    description="Perform comprehensive testing on the game to identify and fix bugs.",
    expected_output='A bug-free, fully functional game ready for release.',
    tools=[development_tool],
    agent=quality_control_engineer,
)

# Frontend Development Task
frontend_development_task = Task(
    description="Develop the frontend of the Flood-It game using Blazor.",
    expected_output='Frontend code for the Flood-It game.',
    tools=[development_tool],
    agent=blazor_frontend_developer,
    output_file='frontend_code.cs',
)

# Backend Development Task
backend_development_task = Task(
    description="Architect and develop the backend of the Flood-It game using C# .NET.",
    expected_output='Backend code for the Flood-It game.',
    tools=[development_tool],
    agent=senior_software_engineer,
    output_file='backend_code.cs',
)

# Adjusting the Crew to Include the New Tasks
game_development_crew = Crew(
    agents=[
        senior_software_engineer,
        blazor_frontend_developer,
        quality_control_engineer,
        chief_quality_control_engineer,
    ],
    tasks=[
        game_design_task,
        backend_development_task,
        frontend_development_task,
        quality_assurance_task,
    ],
    process=Process.sequential
)

# Example kickoff (pseudo-code, adjust based on actual implementation and inputs)
result = game_development_crew.kickoff(inputs={'topic': 'Flood-It game development'})
print(result)



# # Forming the crew
# game_development_crew = Crew(
#     agents=[
#         senior_software_engineer,
#         blazor_frontend_developer,
#         quality_control_engineer,
#         chief_quality_control_engineer,
#     ],
#     tasks=[
#         game_design_task,
#         development_task,
#         quality_assurance_task,
#     ],
#     process=Process.sequential
# )

# # Example kickoff with a dummy topic (replace with actual game details or configurations if needed)
# result = game_development_crew.kickoff(inputs={'topic': 'Flood-It game development'})
# print(result)
