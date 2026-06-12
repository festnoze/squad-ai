# Autospec — backend

Orchestrateur FastAPI qui pilote les agents BMAD (PM → PO → Dev) via le CLI
Claude Code en mode headless, et fait implémenter chaque user story en BDD/TDD
(pytest-bdd) dans un workspace uv dédié.

```powershell
uv sync --extra dev
uv run uvicorn autospec.api.server:app --reload --port 8100
uv run pytest
```
