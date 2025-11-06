# Install uv
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

COPY uv.lock /app/uv.lock
COPY pyproject.toml /app/pyproject.toml

ENV ENVIRONMENT=production

ARG COMMON_TOOLS_INSTALL_MODE="database,advanced,qdrant"
ARG COMMUN_TOOLS_INSTALL_VERSION="1.0.0+build206"
ARG AZURE_FEED_NAME="studi-ia"
ARG AZURE_FEED_TOKEN

ENV AZURE_FEED_URL="https://pkgs.dev.azure.com/${AZURE_FEED_NAME}/_packaging/${AZURE_FEED_NAME}/pypi/simple/"
ENV UV_INDEX_URL="https://xxx:${AZURE_FEED_TOKEN}@pkgs.dev.azure.com/${AZURE_FEED_NAME}/_packaging/${AZURE_FEED_NAME}/pypi/simple/"
ENV UV_EXTRA_INDEX_URL="https://pypi.org/simple"

RUN echo ${UV_INDEX_URL}

RUN uv sync --frozen --no-install-project
RUN uv pip install common-tools[${COMMON_TOOLS_INSTALL_MODE}]==${COMMUN_TOOLS_INSTALL_VERSION} --index-strategy unsafe-best-match

COPY . /app

CMD ["uv", "run", "uvicorn", "src.API.startup:app", "--host", "0.0.0.0", "--port", "8000"]
