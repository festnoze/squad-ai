import os
import sys
import pytest

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from agents.shared_tools import run_linter


def get_python_files(directory):
    """Recursively find all Python files in the given directory."""
    python_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    return python_files


def test_linter_on_project():
    """Test that runs the linter on all Python files in the project.
    Results are saved to a file instead of being printed to the console.
    """
    # Get the project root directory
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    src_dir = os.path.join(project_root, 'src')
    tests_dir = os.path.join(project_root, 'tests')
    
    # Get all Python files in the project
    python_files = get_python_files(src_dir) + get_python_files(tests_dir)
    
    # Dictionary to store linting results
    linting_results = {}
    all_passed = True
    
    # Create output file with timestamp
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_file_path = os.path.join(project_root, f"lint_results_{timestamp}.txt")
    
    with open(output_file_path, 'w') as output_file:
        output_file.write(f"Linting Results - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        output_file.write("=" * 50 + "\n\n")
        
        # Run linter on each Python file
        for file_path in python_files:
            rel_path = os.path.relpath(file_path, project_root)
            output_file.write(f"Linting {rel_path}...\n")
            result = run_linter(file_path)
            linting_results[file_path] = result
            
            if not result['success']:
                all_passed = False
                output_file.write(f"Found {len(result['issues'])} issues:\n")
                for issue in result['issues']:
                    output_file.write(f"  {issue.split(':')[-1].strip()}\n")
            else:
                output_file.write("No issues found.\n")
            output_file.write("\n")
        
        # Create a summary report
        output_file.write("\n===== Linting Summary =====\n")
        total_issues = sum(len(result['issues']) for result in linting_results.values())
        output_file.write(f"Total files checked: {len(python_files)}\n")
        output_file.write(f"Files with issues: {sum(1 for result in linting_results.values() if not result['success'])}\n")
        output_file.write(f"Total issues found: {total_issues}\n")
    
    print(f"Linting results saved to: {output_file_path}")
    
    # Optionally fail the test if linting issues were found
    # Uncomment the following line to make the test fail when linting issues are found
    # assert all_passed, f"Linting failed with {total_issues} issues in the codebase"


def test_linter_on_specific_file():
    """Test that demonstrates how to run the linter on a specific file."""
    # Get the path to a specific file
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    shared_tools_path = os.path.join(project_root, 'src', 'agents', 'shared_tools.py')
    
    # Run linter on the specific file
    result = run_linter(shared_tools_path)
    
    # Print results
    print(f"\nLinting {os.path.relpath(shared_tools_path, project_root)}...")
    if not result['success']:
        print(f"Found {len(result['issues'])} issues:")
        for issue in result['issues']:
            print(f"  {issue}")
    else:
        print("No issues found.")
    
    # This is an example of how you could make assertions about the linting results
    # For example, if you expect a file to be lint-free:
    # assert result['success'], f"Expected {shared_tools_path} to be lint-free, but found issues"


if __name__ == "__main__":
    # This allows running the tests directly from this file
    pytest.main(['-xvs', __file__])
