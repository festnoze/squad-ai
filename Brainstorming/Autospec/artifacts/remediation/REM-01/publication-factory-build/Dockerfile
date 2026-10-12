# Trusted supervisor TEST recipe. Only factory manifests enter the networked
# builder. Tests run separately as nonroot/readOnly/NETNONE without Docker socket.
FROM ghcr.io/astral-sh/uv@sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58
WORKDIR /factory
COPY pyproject.toml uv.lock ./
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_NO_CONFIG=1 UV_CACHE_DIR=/tmp/uv-cache UV_DEFAULT_INDEX=https://pypi.org/simple
RUN uv sync --locked --extra dev --no-install-project --no-build --no-config
ENV HOME=/tmp PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/factory/backend
USER 65532:65532
ENTRYPOINT ["/opt/venv/bin/python", "-m", "pytest"]
