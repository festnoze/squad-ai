"""V1 agents package.

Contains the three agent roles used by the orchestration service:

- `OrchestratorAgent` — decides which tasks to run next.
- `DevAgent` — produces real code for a single task.
- `QaAgent` — reviews the dev output and returns approved / rejected.

The agents are currently implemented on top of `common_tools.llm.Llm`
(the same LLM helper used by the chat scoping agent). The ADK entrypoint
is stubbed but not wired because the user does not have a Google API key
yet — switching to ADK will only require changing `AGENT_ENGINE=adk` in
the environment and filling in the stub. See `app.agents.engine` for
details.
"""

from app.agents.dev_agent import DevAgent, DevAgentResult, DevFileOutput
from app.agents.orchestrator_agent import (
    OrchestratorAgent,
    OrchestratorDecision,
)
from app.agents.qa_agent import QaAgent, QaAgentResult, QaVerdict

__all__ = [
    "DevAgent",
    "DevAgentResult",
    "DevFileOutput",
    "OrchestratorAgent",
    "OrchestratorDecision",
    "QaAgent",
    "QaAgentResult",
    "QaVerdict",
]
