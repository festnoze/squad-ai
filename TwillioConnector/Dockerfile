# Define Python version to use
FROM python:3.12.1-slim

# Set the working directory inside the container
WORKDIR /

# Define the default python path
ENV PYTHONPATH=/src

# Define general docker variables values (application host and port)
ENV HOST_URI=0.0.0.0
ENV PORT=8301

# Overriden values of API environment variables (defined in '.env' file), to be docker-specific
ENV HTTP_SCHEMA="http"
ENV EXTERNAL_API_HOST="studi-website-rag-api"
ENV EXTERNAL_API_PORT="8281"
ENV QUERY_EXTERNAL_ENDPOINT_URL="/rag/inference/no-conversation/ask-question"
ENV QUERY_EXTERNAL_ENDPOINT_URL_STREAMING="/rag/inference/no-conversation/ask-question/stream"
ENV STREAMING_RESPONSE=True

# Copy the dependencies file and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project content into the container
COPY . .

# Clean up log files from previous runs (if any)
RUN rm -rf /outputs/logs/{*,.*}

# Expose the defined port to allow external access
EXPOSE $PORT

# Start the application using uvicorn with the defined host and port
CMD ["sh", "-c", "python -m uvicorn src.api.startup:app --host $HOST_URI --port $PORT --log-level error"]