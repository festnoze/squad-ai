"""Tools for the Eval Maker Harness agents.

Provides file I/O, command execution, and evaluation gating tools
scoped to the workspace directory for safety.
"""

import os
import subprocess

from google.adk.tools.tool_context import ToolContext

WORKSPACE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workspace")
BRIEF_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "brief.md")
INPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "input")


# ============================================================
# FILE I/O TOOLS
# ============================================================


def read_file(file_path: str) -> dict:
    """Reads a file from the workspace, input, or project directory.

    Args:
        file_path: Relative path from workspace root, or 'brief.md',
                   or 'input/<filename>' for input files.

    Returns:
        Dictionary with file content or error message.
    """
    if file_path == "brief.md":
        full_path = BRIEF_PATH
    elif file_path.startswith("input/"):
        full_path = os.path.join(INPUT_DIR, file_path[6:])
    else:
        full_path = os.path.join(WORKSPACE_DIR, file_path)

    if not os.path.exists(full_path):
        return {"status": "error", "message": f"File not found: {file_path}"}

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {
            "status": "success",
            "path": file_path,
            "content": content,
            "size_bytes": len(content.encode("utf-8")),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def write_file(file_path: str, content: str) -> dict:
    """Writes content to a file in the workspace directory.

    Creates parent directories if they don't exist.

    Args:
        file_path: Relative path from workspace root (e.g., 'src/main.py').
        content: The text content to write.

    Returns:
        Dictionary with write confirmation.
    """
    full_path = os.path.join(WORKSPACE_DIR, file_path)

    try:
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return {
            "status": "success",
            "path": file_path,
            "size_bytes": len(content.encode("utf-8")),
            "lines": len(content.splitlines()),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def list_files(directory: str = ".") -> dict:
    """Lists files and directories in the workspace.

    Args:
        directory: Relative path from workspace root. Defaults to root.

    Returns:
        Dictionary with list of entries.
    """
    full_path = os.path.join(WORKSPACE_DIR, directory)

    if not os.path.exists(full_path):
        return {"status": "error", "message": f"Directory not found: {directory}"}

    try:
        entries = []
        for entry in sorted(os.listdir(full_path)):
            entry_path = os.path.join(full_path, entry)
            entries.append({
                "name": entry,
                "type": "directory" if os.path.isdir(entry_path) else "file",
                "size": os.path.getsize(entry_path) if os.path.isfile(entry_path) else None,
            })
        return {"status": "success", "directory": directory, "entries": entries}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============================================================
# COMMAND EXECUTION TOOL
# ============================================================


def run_command(command: str) -> dict:
    """Executes a shell command in the workspace directory.

    Use for: pip install, running tests, starting servers, git operations.
    Commands are executed with a 120-second timeout.

    Args:
        command: The shell command to execute.

    Returns:
        Dictionary with command output, stderr, and exit code.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=WORKSPACE_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return {
            "status": "success" if result.returncode == 0 else "error",
            "exit_code": result.returncode,
            "stdout": result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout,
            "stderr": result.stderr[-1500:] if len(result.stderr) > 1500 else result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Command timed out after 120 seconds."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============================================================
# SPEC & EVALUATION TOOLS
# ============================================================


def save_spec(spec_content: str, tool_context: ToolContext) -> dict:
    """Saves the product specification to workspace/SPEC.md and to state.

    Called by the Planner agent after generating the detailed spec.

    Args:
        spec_content: The complete product specification in markdown.

    Returns:
        Dictionary with save confirmation.
    """
    result = write_file("SPEC.md", spec_content)
    if result["status"] == "success":
        tool_context.state["spec_content"] = spec_content
        tool_context.state["phase"] = "planning_complete"
    return result


def save_build_report(report: str, tool_context: ToolContext) -> dict:
    """Saves a build progress report from the Generator.

    Called by the Generator after completing a build iteration.

    Args:
        report: Summary of what was built, files created, and current status.

    Returns:
        Dictionary with save confirmation.
    """
    iteration = tool_context.state.get("build_iteration", 0) + 1
    tool_context.state["build_iteration"] = iteration
    tool_context.state["build_report"] = report

    result = write_file(f"BUILD_REPORT_v{iteration}.md", report)
    return {**result, "iteration": iteration}


def submit_evaluation(
    score: int, feedback: str, issues: str, tool_context: ToolContext
) -> dict:
    """Submits an evaluation of the generated application.

    If score >= 7, the build is approved and the loop exits.
    If score < 7, feedback is saved for the next Generator iteration.

    Args:
        score: Quality score from 1 to 10 across all success criteria.
        feedback: Detailed evaluation feedback and findings.
        issues: Specific issues that must be fixed (empty string if none).

    Returns:
        Dictionary with evaluation result.
    """
    tool_context.state["eval_score"] = score
    tool_context.state["eval_feedback"] = feedback
    tool_context.state["eval_issues"] = issues

    eval_report = (
        f"# Evaluation Report\n\n"
        f"**Score:** {score}/10\n\n"
        f"## Feedback\n{feedback}\n\n"
        f"## Issues\n{issues if issues else 'None'}\n"
    )
    iteration = tool_context.state.get("build_iteration", 1)
    write_file(f"EVAL_REPORT_v{iteration}.md", eval_report)

    if score >= 7:
        tool_context.actions.escalate = True
        return {
            "status": "approved",
            "score": score,
            "message": f"Build approved with score {score}/10. Exiting loop.",
        }
    return {
        "status": "needs_work",
        "score": score,
        "message": f"Score {score}/10 — below threshold (7). Generator will iterate.",
    }
