.PHONY: install install-aicommontools run check test build clean clean-build docs-build docs-test docs docs-dev lint format help

install: ## Install the virtual environment and install the pre-commit hooks
	@echo "🚀 Creating virtual environment using uv"
	@uv sync
	@uv run pre-commit install
	@echo "🔧 Installing AICommonTools based on ENVIRONMENT"
	@uv run python scripts/install_aicommontools.py

install-aicommontools: ## Install AICommonTools based on ENVIRONMENT variable
	@echo "🔧 Installing AICommonTools based on ENVIRONMENT"
	@uv run python scripts/install_aicommontools.py

run: ## Run the FastAPI app with uvicorn in reload mode on port 8372
	@uv run uvicorn src.startup:app --host 127.0.0.1 --port 8372 --reload


check: ## Run code quality tools.
	@echo "🚀 Checking lock file consistency with 'pyproject.toml'"
	@uv lock --locked
	@echo "🚀 Linting code: Running pre-commit"
	@uv run pre-commit run -a
	@echo "🚀 Static type checking: Running mypy"
	@uv run mypy
	@echo "🚀 Checking for obsolete dependencies: Running deptry"
	@uv run deptry src

test: ## Test the code with pytest
	@echo "🚀 Testing code: Running pytest"
	@uv run python -m pytest --cov --cov-config=pyproject.toml --cov-report=xml

build: clean-build ## Build wheel file
	@echo "🚀 Creating wheel file"
	@uvx --from build pyproject-build --installer uv

clean: ## Remove caches and temporary files
	@uv run python - << 'PY'\nimport os, shutil\nfor p in ['.pytest_cache','.ruff_cache','.mypy_cache','__pycache__','build','dist','.coverage','coverage.xml']:\n    if os.path.isdir(p): shutil.rmtree(p, ignore_errors=True)\n    elif os.path.isfile(p): os.remove(p)\nPY

clean-build: ## Clean build artifacts
	@echo "🚀 Removing build artifacts"
	@uv run python -c "import shutil, os; shutil.rmtree('dist', ignore_errors=True); shutil.rmtree('build', ignore_errors=True)"

docs-build: ## Build documentation to static/docs-site for serving with API
	@echo "📚 Building documentation for API serving"
	@uv run python scripts/build_docs.py

docs-test: ## Test if documentation can be built without warnings or errors
	@uv run mkdocs build -s

docs: ## Start MkDocs development server (separate from API)
	@echo "🚀 Starting MkDocs development server at http://127.0.0.1:8000"
	@uv run mkdocs serve

docs-dev: ## Start MkDocs development server (alias)
	@uv run python scripts/build_docs.py --dev

lint: ## Run linters
	@uv run ruff check .
	@uv run mypy

format: ## Auto-format code
	@uv run ruff check . --fix
	@uv run ruff format .

help:
	@uv run python -c "import re; [[print(f'\033[36m{m[0]:<20}\033[0m {m[1]}') for m in re.findall(r'^([a-zA-Z_-]+):.*?## (.*)$$', open(makefile).read(), re.M)] for makefile in ('$(MAKEFILE_LIST)').strip().split()]"

.DEFAULT_GOAL := help
