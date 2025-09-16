# Use Python 3.12.1-slim as base image
FROM python:3.12.1-slim

# Set the working directory to the container root
WORKDIR /

# Set the default Python path in the container
ENV PYTHONPATH=/app

# Set environment to production to ensure consistent behavior
ENV ENVIRONMENT=production

# Set the application listening address
ENV HOST_URI=0.0.0.0

# Set the application listening port
ENV PORT=8080

# Set the RAG API port and address
ENV RAG_API_IS_SSH=true
ENV RAG_API_HOST=public-website-rag-api-985511623262.europe-west1.run.app
ENV RAG_API_PORT=443

# Copy precompiled wheel packages into the container
#COPY wheels/ /wheels/

# Copy dependency files
COPY pyproject.toml .
COPY uv.lock .

# Install compilation tools necessary for webrtcvad
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv and dependencies
RUN pip install --no-cache-dir uv
RUN uv sync

# Copy the entire project into the container
COPY . .

# Build documentation for production
RUN /.venv/bin/python scripts/build_docs.py || echo "⚠️ Documentation build failed, continuing without docs"

# Modify permissions for the conversation database file
# Obsolete: DB is removed from .dockerignore
#RUN chmod 777 app/database_conversations/conversation_database.db

# Clean the outputs directory of existing data
#RUN rm -rf /outputs/logs/{*,.*}

# Expose the defined port to allow external access to the application
EXPOSE $PORT

# Start the application via Uvicorn with specified parameters
CMD ["sh", "-c", "/.venv/bin/python -m uvicorn app.api.startup:app --host $HOST_URI --port $PORT --log-level error"]
