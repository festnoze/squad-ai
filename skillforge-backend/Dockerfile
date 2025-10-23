# Install uv
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Accept build arguments for Azure Artifacts authentication
ARG AZURE_ARTIFACT_FEED_URL
ARG AZURE_ARTIFACT_FEED_TOKEN
ARG COMMON_TOOLS_INSTALL_MODE=database,advanced,qdrant
ARG AICOMMONTOOLS_VERSION

# Change the working directory to the `app` directory
WORKDIR /app

# Copy the lockfile and `pyproject.toml` into the image
COPY uv.lock /app/uv.lock
COPY pyproject.toml /app/pyproject.toml

# Install dependencies
RUN uv sync --frozen --no-install-project

# Copy the project into the image
COPY . /app

# Set environment variables for AICommonTools installation
ENV ENVIRONMENT=production
ENV AZURE_ARTIFACT_FEED_URL=${AZURE_ARTIFACT_FEED_URL}
ENV AZURE_ARTIFACT_FEED_TOKEN=${AZURE_ARTIFACT_FEED_TOKEN}
ENV COMMON_TOOLS_INSTALL_MODE=${COMMON_TOOLS_INSTALL_MODE}
ENV AICOMMONTOOLS_VERSION=${AICOMMONTOOLS_VERSION}

# Install AICommonTools from Azure Artifacts (scripts already copied in previous step)
RUN uv run python scripts/install_aicommontools.py

# Sync the project
RUN uv sync --frozen

CMD ["uv", "run", "uvicorn", "src.startup:app", "--host", "0.0.0.0", "--port", "8000"]
