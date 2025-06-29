import subprocess
import logging
from langchain.tools import tool

logger = logging.getLogger(__name__)

@tool
def run_linter(file_path: str) -> dict[str, any]:
    """
    Run a Python linter (flake8) on the specified file or directory.
    
    Args:
        file_path: Path to the Python file or directory to lint
        
    Returns:
        dict containing success status and linting results
    """
    try:
        # Run flake8 on the specified file or directory
        result = subprocess.run(
            ["flake8", file_path],
            capture_output=True,
            text=True,
            check=False
        )
        
        # Parse the output
        if result.returncode == 0:
            return {
                "success": True,
                "message": "No linting issues found.",
                "issues": []
            }
        else:
            # Parse the linting issues
            issues = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    issues.append(line)
            
            return {
                "success": False,
                "message": f"Found {len(issues)} linting issues.",
                "issues": issues
            }
    except Exception as e:
        logger.error(f"Error running linter: {str(e)}")
        return {
            "success": False,
            "message": f"Error running linter: {str(e)}",
            "issues": []
        }

@tool
def run_tests(test_path: str | None = None, test_name: str | None = None) -> dict[str, any]:
    """
    Run pytest tests on the specified path or test name.
    
    Args:
        test_path: Optional path to test file or directory
        test_name: Optional specific test name to run (e.g., 'test_file.py::test_function')
        
    Returns:
        dict containing success status and test results
    """
    try:
        # Build the command
        cmd = ["pytest", "-v"]
        
        if test_name:
            cmd.append(test_name)
        elif test_path:
            cmd.append(test_path)
        
        # Run the tests
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
        )
        
        # Parse the output
        output_lines = result.stdout.strip().split('\n')
        
        # Extract test summary
        summary = ""
        for line in reversed(output_lines):
            if "failed" in line and "passed" in line:
                summary = line.strip()
                break
        
        return {
            "success": result.returncode == 0,
            "message": summary if summary else "Tests executed.",
            "output": output_lines,
            "return_code": result.returncode
        }
    except Exception as e:
        logger.error(f"Error running tests: {str(e)}")
        return {
            "success": False,
            "message": f"Error running tests: {str(e)}",
            "output": [],
            "return_code": -1
        }
