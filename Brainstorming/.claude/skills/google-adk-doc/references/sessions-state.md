# Sessions and State Reference

## Table of Contents
- [Session](#session)
- [SessionService](#sessionservice)
- [State](#state)
- [State Key Prefixes](#state-key-prefixes)
- [Accessing State](#accessing-state)
- [Updating State](#updating-state)

## Session

A Session represents a single ongoing conversation between a user and the agent system. It contains the chronological sequence of messages and actions (Events).

## SessionService

Manages session lifecycle (create, retrieve, update, delete).

| Service | Use Case | Persistence |
|---------|----------|-------------|
| `InMemorySessionService` | Local testing, fast development | Lost on restart |
| `DatabaseSessionService` | Production with SQLite/PostgreSQL | Persistent |
| `VertexAiSessionService` | Managed by Vertex AI | Persistent |

## State

Session state is a key-value scratchpad available throughout a conversation. Keys are always strings, values must be serializable (strings, numbers, booleans, lists, dicts).

## State Key Prefixes

| Prefix | Scope | Persistence | Use Cases |
|--------|-------|-------------|-----------|
| (none) | Current session | Service-dependent | Task progress, temporary flags |
| `user:` | All sessions for a user | DB/VertexAI | Preferences, profile details |
| `app:` | All users and sessions | DB/VertexAI | Global settings, shared templates |
| `temp:` | Current invocation only | Never persistent | Intermediate calculations, inter-tool data |

`temp:` state is NOT present across invocations. All tool calls within a single agent turn share the same `InvocationContext` and temporary state.

## Accessing State

### In agent instructions (string templating)

```python
agent = LlmAgent(
    instruction="Write about the theme: {topic}."
    # If session.state['topic'] = "friendship",
    # LLM receives: "Write about the theme: friendship."
)
```

### Storing agent output in state

```python
agent = LlmAgent(
    instruction="Generate a greeting.",
    output_key="last_greeting"
    # Agent's text response is stored in state['last_greeting']
)
```

## Updating State

### Via CallbackContext or ToolContext (recommended)

```python
def my_callback(callback_context: CallbackContext):
    count = callback_context.state.get("user_action_count", 0)
    callback_context.state["user_action_count"] = count + 1
    callback_context.state["temp:last_op"] = "success"
    # Changes auto-captured in event's state_delta
```

```python
def my_tool(query: str, tool_context: ToolContext) -> dict:
    """Process query."""
    tool_context.state["result"] = query.upper()
    return {"status": "success"}
```

### Via EventActions with state_delta

```python
state_changes = {
    "task_status": "active",
    "user:login_count": 1,
    "temp:validation_needed": True
}
actions = EventActions(state_delta=state_changes)
event = Event(author="system", actions=actions)
await session_service.append_event(session, event)
```

### NEVER modify state directly on a retrieved session

```python
# WRONG - bypasses event history, not persistent, not thread-safe
retrieved_session = await session_service.get_session(...)
retrieved_session.state['key'] = value  # DON'T DO THIS
```

Why it fails:
- Bypasses Event History and loses auditability
- Changes won't persist with DatabaseSessionService
- Not thread-safe; risks race conditions
- Doesn't trigger event logic or timestamp updates

## Multi-Agent State Sharing

Sub-agents receive the parent agent's `InvocationContext`, meaning the entire chain of agent calls shares the same invocation ID and `temp:` state. This enables synchronized temporary state across hierarchical agent structures.
