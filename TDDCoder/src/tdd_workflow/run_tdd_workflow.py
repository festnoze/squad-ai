import logging
import sys
import os
import argparse

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tdd_workflow.tdd_workflow_graph import TDDWorkflowGraph
from llms.langchain_factory import LangChainFactory, LangChainAdapterType
from llms.envvar import EnvHelper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Run the TDD Implementation Workflow')
    parser.add_argument('--input', '-i', type=str, required=False,
                        help='Path to the conception output JSON file')
    args = parser.parse_args()
    
    if not args.input:
        # Use bowling_scoring.json as default input
        args.input = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'bowling_scoring.json'))
        print(f"No input file specified. Using default bowling scoring specification: {args.input}")
        
    # Check if input file exists
    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' does not exist.")
        return
    
    # Initialize the LLM
    openai_api_key = EnvHelper.get_openai_api_key()
    llm = LangChainFactory.create_llm(LangChainAdapterType.OpenAI, llm_model_name="gpt-4", temperature=0.5, inference_provider_api_key=openai_api_key)
    
    # Initialize the TDD workflow graph
    tdd_workflow = TDDWorkflowGraph(llm)
    
    print(f"\nStarting TDD implementation workflow with input: '{args.input}'\n")
    
    # Run the workflow
    try:
        import json
        import asyncio
        
        # Load the conception output
        with open(args.input, 'r') as f:
            conception_data = json.load(f)
            
        user_story_spec = conception_data.get("user_story", {}).get("description", "")
        acceptance_tests_gherkin = conception_data.get("scenarios", [])
        
        # Run the workflow asynchronously
        result = asyncio.run(tdd_workflow.run_wo_graph_async(user_story_spec, acceptance_tests_gherkin))
        #result = asyncio.run(tdd_workflow.run_async(user_story_spec, acceptance_tests_gherkin))
        
        if result.get("error"):
            print(f"\nError running TDD implementation workflow: {result.get('error_message')}")
        else:
            print("\nWorkflow completed successfully!")
            # The result of a graph invocation is a dictionary
            print(f"User Story: {result.get('user_story')}")
            print(f"Final Code:\n{result.get('code')}")
        if result.code:
            print("\nLast Implementation:")
            print(result.code)
            
        if result.refactored_code:
            print("\nLast Refactored Code:")
            print(result.refactored_code)
            
    except Exception as e:
        print(f"Error running TDD implementation workflow: {str(e)}")
        import traceback
        traceback.print_exc()
