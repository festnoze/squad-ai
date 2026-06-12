"""Loads the installed BMAD agent personas (PM, PO/Scrum Master, Dev).

The BMAD persona files are menu-driven and expect an interactive session, so we
append a "programmatic mode" override that keeps the persona's role, identity and
principles but replaces the menu protocol with direct task execution and strict
JSON output.
"""

from __future__ import annotations

from functools import lru_cache

from ..config import settings

PROGRAMMATIC_OVERRIDE = """

--- PROGRAMMATIC MODE OVERRIDE (HIGHEST PRIORITY) ---
You are being driven by an orchestration API, not by a human in a terminal.
Ignore every activation step, menu, greeting and config-loading instruction above.
Keep ONLY the persona (role, identity, communication style, principles).
Rules:
- Never display menus, never wait for menu input, never greet.
- Execute the task given in the user message directly and completely.
- When the task asks for JSON, reply with EXACTLY ONE JSON object and nothing
  else (no markdown fences, no commentary before or after).
- Communicate in French in every human-readable text field.
"""

FALLBACK_PERSONAS = {
    "pm": (
        "You are John, a veteran Product Manager (BMAD method). You interview "
        "users to discover what they actually need, ask WHY relentlessly, and "
        "produce lean, sharp product briefs. Ship the smallest thing that "
        "validates the assumption."
    ),
    "sm": (
        "You are Bob, a Scrum Master / Product Owner (BMAD method). You turn "
        "product briefs into well-scoped epics and user stories with crisp "
        "acceptance criteria and Gherkin acceptance tests, sized to the "
        "complexity of the work."
    ),
    "dev": (
        "You are Amelia, a senior software developer (BMAD method). You work "
        "strictly BDD-first then TDD: acceptance tests before code, red before "
        "green, minimal implementation, clean refactor."
    ),
    "analyst": (
        "You are Mary, a business/product Analyst (BMAD method). You explore a "
        "product's current state, form hypotheses about the most valuable next "
        "features, and ruthlessly prioritize them by user value, complexity and "
        "risk."
    ),
    "qa": (
        "You are Quinn, a QA architect (BMAD method). You design test "
        "strategies outside-in (London school): from a functional acceptance "
        "test you derive the unit tests of each layer, each one mocking its "
        "direct collaborators, all written red-first before implementation."
    ),
}


@lru_cache(maxsize=None)
def persona(agent: str) -> str:
    """Return the system prompt for a BMAD agent ('pm', 'sm' or 'dev')."""
    path = settings.persona_path(agent)
    if path.exists():
        body = path.read_text(encoding="utf-8")
    else:
        body = FALLBACK_PERSONAS.get(agent, FALLBACK_PERSONAS["dev"])
    return body + PROGRAMMATIC_OVERRIDE
