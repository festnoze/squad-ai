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
def save_code(code: str) -> dict:
    """Saves the written code and returns metrics.

    Args:
        code: The Python source code to save.

    Returns:
        Dictionary with code metrics.
    """
    line_count = len(code.strip().splitlines())
    return {"status": "success", "line_count": line_count}


def submit_security_review(findings: list[str], risk_level: str) -> dict:
    """Submits security review findings.

    Args:
        findings: List of security issues found.
        risk_level: Overall risk level: "LOW", "MEDIUM", "HIGH", or "CRITICAL".

    Returns:
        Dictionary confirming the review.
    """
    return {
        "status": "success",
        "findings_count": len(findings),
        "findings": findings,
        "risk_level": risk_level,
    }


def submit_performance_review(findings: list[str], rating: str) -> dict:
    """Submits performance review findings.

    Args:
        findings: List of performance issues or suggestions.
        rating: Performance rating: "GOOD", "ACCEPTABLE", or "NEEDS_WORK".

    Returns:
        Dictionary confirming the review.
    """
    return {
        "status": "success",
        "findings_count": len(findings),
        "findings": findings,
        "rating": rating,
    }


def submit_style_review(findings: list[str], pep8_compliant: bool) -> dict:
    """Submits code style review findings.

    Args:
        findings: List of style issues found.
        pep8_compliant: Whether the code follows PEP 8 guidelines.

    Returns:
        Dictionary confirming the review.
    """
    return {
        "status": "success",
        "findings_count": len(findings),
        "findings": findings,
        "pep8_compliant": pep8_compliant,
    }


# --- Stage 1: Writer ---
writer_agent = Agent(
    name="writer",
    model="gemini-2.5-flash",
    description="Writes Python code.",
    instruction=(
        "Write Python code for the user's request. "
        "Use save_code to save it. Present the code."
    ),
    tools=[save_code],
    output_key="generated_code",
)

# --- Stage 2: Parallel reviewers ---
security_reviewer = Agent(
    name="security_reviewer",
    model="gemini-2.5-flash",
    description="Checks code for security vulnerabilities.",
    instruction=(
        "Analyze this code for security vulnerabilities (SQL injection, XSS, "
        "input validation, etc.):\n\n{generated_code}\n\n"
        "Use submit_security_review to record your findings and risk level."
    ),
    tools=[submit_security_review],
    output_key="security_review",
)

performance_reviewer = Agent(
    name="performance_reviewer",
    model="gemini-2.5-flash",
    description="Analyzes code performance.",
    instruction=(
        "Analyze this code for performance issues (complexity, memory usage, "
        "I/O patterns, etc.):\n\n{generated_code}\n\n"
        "Use submit_performance_review to record your findings and rating."
    ),
    tools=[submit_performance_review],
    output_key="performance_review",
)

style_reviewer = Agent(
    name="style_reviewer",
    model="gemini-2.5-flash",
    description="Reviews code style and PEP 8 compliance.",
    instruction=(
        "Review this code for style, readability, and PEP 8 compliance:\n\n"
        "{generated_code}\n\n"
        "Use submit_style_review to record your findings."
    ),
    tools=[submit_style_review],
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
