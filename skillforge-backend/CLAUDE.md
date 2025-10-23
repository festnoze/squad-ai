# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SkillForge API is a FastAPI-based backend service providing one-to-one AI learning tutor functionality for students. The project uses Python 3.9+ with UV for dependency management and follows a clean architecture pattern with distinct layers.

## Development Environment Setup

**1. Create `.env` file from template:**
```bash
cp .env.sample .env
```

Edit `.env` and configure:
- `ENVIRONMENT=development` for local dev
- `AICOMMONTOOLS_LOCAL_PATH=C:/Dev/IA/AzureDevOps/ai-commun-tools` (adjust to your local path)
- `COMMON_TOOLS_INSTALL_MODE=database` (install only database dependencies, excluding pinecone and ml)

**2. Install dependencies and pre-commit hooks:**
```bash
make install
```

This command:
- Creates a virtual environment using UV
- Installs all dependencies from pyproject.toml
- Sets up pre-commit hooks for code quality
- **Installs AICommonTools based on ENVIRONMENT variable**
  - Development: Editable install from local path with extras from `COMMON_TOOLS_INSTALL_MODE`
  - Built-lib: Install from wheel file in `wheels/` folder with extras
  - Production: Install from Azure Artifacts feed with extras

**Always activate the virtual environment before running any commands:**
```bash
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Unix/macOS
```

**To reinstall AICommonTools only:**
```bash
make install-aicommontools
```

## Common Commands

### Running the Application

```bash
# Run the FastAPI app with hot reload on port 8372
make run

# Or directly with uvicorn
uv run uvicorn src.startup:app --host 127.0.0.1 --port 8372 --reload
```

The app starts at `http://localhost:8372` with:
- API docs at `/docs` (Swagger UI) → `http://localhost:8372/docs`
- ReDoc at `/redoc` → `http://localhost:8372/redoc`
- Site documentation at `/docs-site/` (if built)

### Code Quality & Testing

```bash
# Run all code quality checks (pre-commit, mypy, deptry)
make check

# Run tests with coverage
make test

# Run linters only
make lint

# Auto-format code
make format

# Run pre-commit hooks manually
uv run pre-commit run -a
```

### Running Single Tests

```bash
# Activate venv first, then run specific test
.venv\Scripts\activate
uv run python -m pytest tests/test_specific.py
uv run python -m pytest tests/test_specific.py::test_function_name
```

### Documentation

```bash
# Build and serve documentation locally
make docs

# Test documentation build
make docs-test
```

### Build & Clean

```bash
# Build wheel package
make build

# Clean caches and temporary files
make clean
```

## Architecture

### Layered Structure

The codebase follows a **3-layer architecture** pattern:

1. **facade Layer** (`src/facade/`): HTTP endpoints and request/response handling
   - Contains FastAPI facade with endpoint definitions
   - Handles request validation and response serialization
   - Example: `base_router.py` contains the `/health` endpoint

2. **Application/Service Layer** (`src/application/`): Business logic
   - Contains service classes that implement business rules
   - Orchestrates between facade and repositories
   - Example: `thread_service.py` provides service methods

3. **Infrastructure/Repository Layer** (`src/infrastructure/`): Data access
   - Contains repository classes for data persistence
   - Abstracts database/external service interactions
   - Example: `thread_repository.py` handles data operations

### Key Files

- **`src/startup.py`**: Application entry point
  - Initializes the FastAPI app via `ApiConfig.create_app()`
  - Handles startup tasks (clearing logs, etc.)
  - Environment variables loaded here

- **`src/api_config.py`**: FastAPI app configuration
  - Creates and configures the FastAPI application
  - Sets up CORS, middleware, logging, and documentation serving
  - Centralized exception handling via middleware
  - Lifespan management for startup/shutdown

- **`src/envvar.py`**: Environment variable management
  - `EnvHelper` class centralizes all environment variable access
  - Supports loading from `.env` files and custom env files
  - Contains configuration for OpenAI, calendar, business hours, tracking, etc.

### Environment Configuration

- Environment variables are managed through `EnvHelper` class
- Load `.env` file at project root or custom files via `CUSTOM_ENV_FILES`
- Key variables:
  - `ENVIRONMENT`: Environment mode (development/production) - **Critical for AICommonTools installation**
  - `REMOVE_LOGS_UPON_STARTUP`: Clear logs on startup (true/false)
  - `SERVE_DOCUMENTATION`: Serve MkDocs docs at `/docs-site/` (true/false)

### AICommonTools Dependency Management

The project uses a custom installation script (`scripts/install_aicommontools.py`) to handle environment-specific installation of the AICommonTools library with flexible dependency management.

**Dependency Groups** (controlled via `COMMON_TOOLS_INSTALL_MODE`):
The common_tools library supports optional dependency groups to minimize installation size:
- **Core dependencies** (always installed): ChromaDB, LangChain, OpenAI, etc.
- **database**: Database support (SQLAlchemy, asyncpg, psycopg2-binary) - **Required for SkillForge**
- **qdrant**: Qdrant vector DB (qdrant-client, langchain-qdrant)
- **pinecone**: Pinecone vector DB (⚠️ requires C++ redistributable) - **Not needed for SkillForge**
- **ml**: ML/scientific computing (scikit-learn, scipy, pandas) - **Not needed for SkillForge**
- **advanced**: Advanced AI features (langgraph, langsmith, ragas)
- **full**: All optional dependencies

**For SkillForge Backend**, set `COMMON_TOOLS_INSTALL_MODE=database` to install only database dependencies (excluding pinecone and ml).

**Development Mode** (`ENVIRONMENT=development`):
- Installs AICommonTools as an editable package from local path
- Configure via: `AICOMMONTOOLS_LOCAL_PATH` in `.env`
- Command executed: `uv pip install -e "common-tools[database] @ C:/Dev/IA/AzureDevOps/ai-commun-tools"`
- Allows live updates to the library during development

**Built-lib Mode** (`ENVIRONMENT=built-lib`):
- Installs AICommonTools from a wheel file in `wheels/` folder
- Command executed: `uv pip install wheels/common_tools-{version}-py3-none-any.whl[database]`
- Used for testing production builds locally

**Production Mode** (`ENVIRONMENT=production`):
- Installs AICommonTools from Azure Artifacts private feed
- Required environment variables:
  - `AZURE_ARTIFACT_FEED_URL`: Azure Artifacts feed URL
  - `AZURE_ARTIFACT_FEED_TOKEN`: Personal Access Token for authentication
  - `AICOMMONTOOLS_VERSION`: (Optional) Specific version to install
  - `COMMON_TOOLS_INSTALL_MODE`: (Optional) Extras to install, defaults to "database"
- Command executed: `uv pip install common-tools[database]==version --index-url {feed_url}`
- Used in Docker deployments to Azure

**Manual installation:**
```bash
make install-aicommontools
```

### Async Conventions

- **All async methods MUST be prefixed with `a`**
- Example: `async def ahealth_check()`, `async def atest()`
- This is a project-wide naming convention

## Code Quality Configuration

### Ruff (Linter & Formatter)

- **Line length**: 220 characters
- **Target Python**: 3.12
- **Enabled rules**: E (errors), F (pyflakes), W (warnings), I (imports)
- **Ignored rules**: E501 (line length), I001 (import sorting), W293 (blank line whitespace), TRY003
- **Quote style**: Double quotes

### MyPy (Type Checking)

- Strict type checking enabled
- `disallow_untyped_defs = true`
- `disallow_any_unimported = true`
- Files checked: `src/`

### Pre-commit Hooks

Configured hooks run automatically on commit:
- Check YAML/TOML/JSON validity
- Check for merge conflicts
- Ruff check with auto-fix
- Ruff format
- Trailing whitespace removal
- End-of-file fixer

## Testing

- Tests located in `tests/` directory (currently empty)
- Use pytest with async support (`asyncio_mode = "auto"`)
- Coverage configuration in `pyproject.toml`
- Run with coverage: `make test`

## Documentation

- MkDocs-based documentation
- Configuration in `mkdocs.yml`
- Source files in `docs/` directory
- Built documentation served at `/docs-site/` when `SERVE_DOCUMENTATION=true`
- Material theme with Python docstring support

## Adding New Features

When adding new endpoints/features:

1. **Create router** in `src/facade/` with request/response models
2. **Create service** in `src/application/` with business logic
3. **Create repository** in `src/infrastructure/` for data access
4. **Register router** in `src/api_config.py` using `app.include_router()`
5. **Follow async naming convention**: prefix async methods with `a`
6. **Add tests** in `tests/` directory
7. **Update documentation** if adding user-facing features

## Key Dependencies

- **FastAPI**: Web framework (>=0.118.0)
- **Uvicorn**: ASGI server with standard extras (>=0.37.0)
- **Pytest**: Testing framework (>=8.4.2)
- **Ruff**: Fast Python linter and formatter
- **MyPy**: Static type checker
- **Pre-commit**: Git hook framework
- **MkDocs**: Documentation generator with Material theme
