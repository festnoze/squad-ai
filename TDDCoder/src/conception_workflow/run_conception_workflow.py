import logging
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from langchain_openai import ChatOpenAI
from conception_workflow.conception_workflow_graph import ConceptionWorkflowGraph

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

def main():
    # Check if OpenAI API key is set
    if 'OPENAI_API_KEY' not in os.environ:
        print("Error: OPENAI_API_KEY environment variable is not set.")
        print("Please set your OpenAI API key using:")
        print("export OPENAI_API_KEY='your-api-key'  # On Linux/Mac")
        print("set OPENAI_API_KEY=your-api-key  # On Windows")
        return
    
    # Initialize the LLM
    llm = ChatOpenAI(
        temperature=0.2,
        model="gpt-4",  # Use an appropriate model
    )
    
    # Create the workflow
    workflow = ConceptionWorkflowGraph(llm)
    
    # Get user request
    print("\n=== Conception Workflow ===\n")
    print("This workflow will help you create a user story and BDD scenarios from your requirements.")
    user_request = input("\nPlease enter your feature request: ")
    
    if not user_request:
        print("No request provided. Exiting.")
        return
    
    # Run the workflow
    print("\nProcessing your request...\n")
    result = workflow.run(user_request)
    
    # Display the results
    print("\n=== Conception Results ===\n")
    
    print("User Story:")
    print(f"As a {result.user_story.get('role', '')}")
    print(f"I want to {result.user_story.get('goal', '')}")
    print(f"So that {result.user_story.get('benefit', '')}")
    
    print("\nBDD Scenarios:")
    for i, scenario in enumerate(result.scenarios, 1):
        print(f"\nScenario {i}: {scenario.get('title', '')}")
        print(f"  Given {scenario.get('given', '')}")
        print(f"  When {scenario.get('when', '')}")
        print(f"  Then {scenario.get('then', '')}")
    
    # Save the results to a file for the implementation workflow
    output_file = "conception_output.json"
    import json
    with open(output_file, "w") as f:
        json.dump({
            "user_story": result.user_story,
            "scenarios": result.scenarios
        }, f, indent=2)
    
    print(f"\nResults saved to {output_file}. You can now use these for the implementation workflow.")

if __name__ == "__main__":
    main()
