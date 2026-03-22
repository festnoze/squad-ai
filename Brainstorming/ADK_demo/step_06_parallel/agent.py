"""Step 6 - ParallelAgent (Concurrent Execution).

Concepts: ParallelAgent, concurrent sub-agents, nesting workflow agents,
          no state sharing between parallel branches during execution.

Pipeline: Writer -> Parallel(Security + Perf + Style) -> Synthesizer

Try in adk web:
  - "Write a function to transfer money between accounts"
  (Pipeline: write code -> 3 parallel reviews -> synthesis report)
"""

from google.adk.agents import Agent, ParallelAgent, SequentialAgent


# --- Tools ---
def generate_code(specification: str) -> dict:
    """Generates Python code from a specification.

    Args:
        specification: What the code should do.

    Returns:
        Dictionary with generated code.
    """
    return {
        "status": "success",
        "code": (
            "def transfer(amount, dest):\n"
            "    db.execute(f'UPDATE accounts SET balance={amount} WHERE id={dest}')\n"
            "    return True\n"
        ),
    }


def check_security(code: str) -> dict:
    """Checks Python code for security vulnerabilities.

    Args:
        code: The Python source code to analyze.

    Returns:
        Dictionary with security findings.
    """
    return {
        "status": "success",
        "findings": [
            {"severity": "CRITICAL", "issue": "SQL injection via f-string formatting"},
            {"severity": "HIGH", "issue": "No input validation on amount parameter"},
        ],
    }


def check_performance(code: str) -> dict:
    """Analyzes Python code for performance issues.

    Args:
        code: The Python source code to analyze.

    Returns:
        Dictionary with performance findings.
    """
    return {
        "status": "success",
        "findings": [
            {"severity": "MEDIUM", "issue": "Direct DB call without connection pooling"},
            {"severity": "LOW", "issue": "No caching strategy for repeated queries"},
        ],
    }


def check_style(code: str) -> dict:
    """Reviews Python code for PEP 8 compliance and style.

    Args:
        code: The Python source code to review.

    Returns:
        Dictionary with style findings.
    """
    return {
        "status": "success",
        "findings": [
            {"severity": "WARNING", "issue": "Missing type hints on all parameters"},
            {"severity": "WARNING", "issue": "Missing docstring"},
            {"severity": "INFO", "issue": "Variable name 'dest' should be more descriptive"},
        ],
    }


# --- Stage 1: Writer ---
writer_agent = Agent(
    name="writer",
    model="gemini-2.5-flash",
    description="Writes Python code.",
    instruction="Generate code for the user's request using generate_code. Present the code.",
    tools=[generate_code],
    output_key="generated_code",
)

# --- Stage 2: Parallel reviewers ---
security_reviewer = Agent(
    name="security_reviewer",
    model="gemini-2.5-flash",
    description="Checks code for security vulnerabilities.",
    instruction="Analyze this code for security issues using check_security:\n\n{generated_code}",
    tools=[check_security],
    output_key="security_review",
)

performance_reviewer = Agent(
    name="performance_reviewer",
    model="gemini-2.5-flash",
    description="Analyzes code performance.",
    instruction="Analyze this code for performance issues using check_performance:\n\n{generated_code}",
    tools=[check_performance],
    output_key="performance_review",
)

style_reviewer = Agent(
    name="style_reviewer",
    model="gemini-2.5-flash",
    description="Reviews code style and PEP 8 compliance.",
    instruction="Review this code for style issues using check_style:\n\n{generated_code}",
    tools=[check_style],
    output_key="style_review",
)

parallel_review = ParallelAgent(
    name="parallel_review",
    description="Runs all three code reviewers concurrently.",
    sub_agents=[security_reviewer, performance_reviewer, style_reviewer],
)

# --- Stage 3: Synthesizer ---
synthesizer_agent = Agent(
    name="synthesizer",
    model="gemini-2.5-flash",
    description="Combines all review results into a unified report.",
    instruction=(
        "Compile the three review results into one unified report.\n\n"
        "Security Review:\n{security_review}\n\n"
        "Performance Review:\n{performance_review}\n\n"
        "Style Review:\n{style_review}\n\n"
        "Provide an overall score (1-10) and a PASS/FAIL verdict."
    ),
    output_key="final_report",
)

# --- Full pipeline: write -> parallel review -> synthesize ---
root_agent = SequentialAgent(
    name="reviewed_code_pipeline",
    description="Write code, review in parallel, synthesize results.",
    sub_agents=[writer_agent, parallel_review, synthesizer_agent],
)
