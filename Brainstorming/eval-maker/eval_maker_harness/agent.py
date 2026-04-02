"""Eval Maker Harness — 4-Agent Architecture using Google ADK.

Architecture:
  orchestrator (SequentialAgent)
    +-- planner (Agent) — reads brief + target prompt, produces SPEC.md
    +-- build_loop (LoopAgent, max_iterations=3)
          +-- generator (Agent) — implements the application
          +-- evaluator (Agent) — tests and scores the build
"""

from google.adk.agents import Agent, LoopAgent, SequentialAgent

from .prompts import (
    EVALUATOR_INSTRUCTION,
    GENERATOR_INSTRUCTION,
    ORCHESTRATOR_INSTRUCTION,
    PLANNER_INSTRUCTION,
)
from .tools import (
    list_files,
    read_file,
    run_command,
    save_build_report,
    save_spec,
    submit_evaluation,
    write_file,
)

MODEL = "gemini-2.5-flash"

# ============================================================
# 1. PLANNER — Produces SPEC.md from brief + target prompt
# ============================================================

planner = Agent(
    name="planner",
    model=MODEL,
    description="Reads the product brief and target prompt, produces a detailed SPEC.md.",
    instruction=PLANNER_INSTRUCTION,
    tools=[read_file, save_spec],
    output_key="spec_content",
)

# ============================================================
# 2. GENERATOR — Builds the application from SPEC.md
# ============================================================

generator = Agent(
    name="generator",
    model=MODEL,
    description="Implements the Eval Suite Generator application based on the spec.",
    instruction=GENERATOR_INSTRUCTION,
    tools=[read_file, write_file, list_files, run_command, save_build_report],
    output_key="build_report",
)

# ============================================================
# 3. EVALUATOR — Tests and scores the build
# ============================================================

evaluator = Agent(
    name="evaluator",
    model=MODEL,
    description="Tests the generated application against success criteria and scores it.",
    instruction=EVALUATOR_INSTRUCTION,
    tools=[read_file, list_files, run_command, submit_evaluation],
    output_key="eval_feedback",
)

# ============================================================
# 4. BUILD LOOP — Generator + Evaluator iterate until approved
# ============================================================

build_loop = LoopAgent(
    name="build_loop",
    description="Iterates Generator and Evaluator until build score >= 7/10.",
    sub_agents=[generator, evaluator],
    max_iterations=3,
)

# ============================================================
# ROOT AGENT: Full Harness Pipeline
# ============================================================

root_agent = SequentialAgent(
    name="eval_maker_harness",
    description=ORCHESTRATOR_INSTRUCTION,
    sub_agents=[planner, build_loop],
)
