# Agent Types Reference

## Table of Contents
- [LlmAgent Constructor Parameters](#llmagent-constructor-parameters)
- [Dynamic Instructions](#dynamic-instructions)
- [SequentialAgent](#sequentialagent)
- [ParallelAgent](#parallelagent)
- [LoopAgent](#loopagent)
- [Structured Output](#structured-output)
- [LLM Configuration](#llm-configuration)

## LlmAgent Constructor Parameters

`Agent` is an alias for `LlmAgent`. Both are imported from `google.adk.agents`.

| Parameter | Description |
|-----------|-------------|
| `name` | Unique string identifier (required) |
| `model` | LLM model string, e.g. `"gemini-2.5-flash"` (required) |
| `instruction` | String or callable guiding agent behavior |
| `description` | Concise capability summary (used by parent agents for routing) |
| `tools` | List of tools (functions, FunctionTool, BaseTool, AgentTool) |
| `sub_agents` | List of child agents for delegation |
| `output_key` | State key to store agent's final text response |
| `output_schema` | Pydantic BaseModel enforcing structured JSON output |
| `input_schema` | Pydantic BaseModel defining expected input structure |
| `include_contents` | `'default'` (history) or `'none'` (stateless) |
| `generate_content_config` | Fine-tune LLM: temperature, max_output_tokens, safety_settings |
| `planner` | `BuiltInPlanner` or `PlanReActPlanner` for multi-step reasoning |
| `before_agent_callback` | Callback before agent processing |
| `after_agent_callback` | Callback after agent processing |
| `before_model_callback` | Callback before LLM call |
| `after_model_callback` | Callback after LLM response |
| `before_tool_callback` | Callback before tool execution |
| `after_tool_callback` | Callback after tool execution |

## Dynamic Instructions

### State variable templating

```python
agent = LlmAgent(
    instruction="Help the user. Their name is {user_name}. Topic: {topic}.",
    # {var} reads from session state
    # {artifact.var} reads artifact text content
    # {var?} ignores error if variable missing
)
```

### Callable instruction provider

Use when instructions contain literal curly braces or need runtime logic:

```python
from google.adk.agents import ReadonlyContext

def my_instruction_provider(context: ReadonlyContext) -> str:
    user = context.state.get("user_name", "friend")
    return f'You are helping {user}. Format as JSON: {{"result": "<value>"}}'

agent = LlmAgent(instruction=my_instruction_provider)
```

## SequentialAgent

Executes sub-agents in fixed order. Deterministic, non-LLM-powered. Sub-agents share data via session state using `output_key`.

```python
from google.adk.agents import SequentialAgent, LlmAgent

code_writer = LlmAgent(
    name="CodeWriter",
    model="gemini-2.5-flash",
    instruction="Write Python code based on the user's request.",
    output_key="generated_code"
)

code_reviewer = LlmAgent(
    name="CodeReviewer",
    model="gemini-2.5-flash",
    instruction="Review this code: {generated_code}. Provide feedback.",
    output_key="review_comments"
)

code_refactorer = LlmAgent(
    name="CodeRefactorer",
    model="gemini-2.5-flash",
    instruction="Refactor this code: {generated_code} based on: {review_comments}.",
    output_key="final_code"
)

pipeline = SequentialAgent(
    name="code_pipeline",
    sub_agents=[code_writer, code_reviewer, code_refactorer]
)
```

**Data flow pattern:** Agent 1 writes via `output_key` -> Agent 2 reads via `{state_var}` in instruction.

## ParallelAgent

Executes sub-agents concurrently. Each sub-agent runs in its own branch with **no automatic state/history sharing** between branches during execution.

```python
from google.adk.agents import ParallelAgent, LlmAgent

researcher_energy = LlmAgent(
    name="EnergyResearcher",
    model="gemini-2.5-flash",
    instruction="Research renewable energy trends.",
    output_key="energy_research"
)

researcher_ev = LlmAgent(
    name="EVResearcher",
    model="gemini-2.5-flash",
    instruction="Research electric vehicle market.",
    output_key="ev_research"
)

parallel_research = ParallelAgent(
    name="parallel_research",
    sub_agents=[researcher_energy, researcher_ev]
)
```

**Combining with SequentialAgent** to merge parallel results:

```python
merger = LlmAgent(
    name="Merger",
    model="gemini-2.5-flash",
    instruction="Combine: {energy_research} and {ev_research}.",
    output_key="merged"
)

pipeline = SequentialAgent(
    name="full_pipeline",
    sub_agents=[parallel_research, merger]
)
```

## LoopAgent

Executes sub-agents iteratively until `max_iterations` or escalation.

```python
from google.adk.agents import LoopAgent, LlmAgent

writer = LlmAgent(
    name="Writer",
    model="gemini-2.5-flash",
    instruction="Write or improve the document based on feedback: {feedback}.",
    output_key="draft"
)

critic = LlmAgent(
    name="Critic",
    model="gemini-2.5-flash",
    instruction="Review the draft: {draft}. If good, use the approve tool. Otherwise provide feedback.",
    output_key="feedback",
    tools=[approve_tool]
)

loop = LoopAgent(
    name="writing_loop",
    sub_agents=[writer, critic],
    max_iterations=5
)
```

**Termination via escalation in a tool:**
```python
def approve(tool_context) -> str:
    """Approve the current draft and stop the loop."""
    tool_context.actions.escalate = True
    return "Approved!"
```

## Structured Output

Force structured JSON output using `output_schema`:

```python
from pydantic import BaseModel, Field

class CityInfo(BaseModel):
    city: str = Field(description="The city name")
    population: int = Field(description="Population count")
    country: str = Field(description="Country name")

agent = LlmAgent(
    name="city_info_agent",
    model="gemini-2.5-flash",
    instruction="Provide city information.",
    output_schema=CityInfo
)
```

> Using `output_schema` with `tools` simultaneously is only reliably supported by Gemini 3.0+.

## LLM Configuration

```python
from google.genai import types

agent = LlmAgent(
    name="precise_agent",
    model="gemini-2.5-flash",
    instruction="Be precise and concise.",
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
        max_output_tokens=500,
    )
)
```

## Multi-Agent Hierarchical Delegation

The coordinator's LLM decides which sub-agent to delegate to based on `description` fields:

```python
researcher = LlmAgent(
    name="Researcher",
    model="gemini-2.5-flash",
    description="Researches topics using web search.",
    instruction="Research topics thoroughly.",
    tools=[google_search]
)

writer = LlmAgent(
    name="Writer",
    model="gemini-2.5-flash",
    description="Writes clear content based on research.",
    instruction="Write clear, engaging content."
)

coordinator = LlmAgent(
    name="Coordinator",
    model="gemini-2.5-flash",
    instruction="Delegate research to Researcher and writing to Writer.",
    sub_agents=[researcher, writer]
)
```
