# Define Python version to use
FROM python:3.12.1-slim

# Set the working directory inside the container
WORKDIR /

# Define the default python path
ENV PYTHONPATH=/

# Define general docker variables values (application host and port)
ENV HOST_URI=0.0.0.0
ENV PORT=8280

# Overriden values of API environment variables (defined in '.env' file), to be docker-specific
ENV HTTP_SCHEMA="http"
ENV EXTERNAL_API_HOST="studi-website-rag-api"
ENV EXTERNAL_API_PORT="8281"

# Copie les packages wheel précompilés dans le container
COPY wheels/ /wheels/

# Copie le fichier des dépendances communes (non utilisé pour l'installation ici)
COPY requirements_common.txt .

# Options d'installation alternatives (non activées)
# RUN pip install /wheels/*.whl
# RUN pip install --no-cache-dir -r requirements_common.txt

# Copy the dependencies file and install them
COPY requirements.txt .
COPY requirements_docker.txt .
RUN pip install --no-cache-dir -r requirements_docker.txt

# Copy the entire project content into the container
COPY . .

# Clean up log files from previous runs (if any)
RUN rm -rf /outputs/logs/{*,.*}

# Expose the defined port to allow external access
EXPOSE $PORT

# Start the application using streamlit on the defined host and port
CMD ["sh", "-c", "streamlit run startup.py --server.address=$HOST_URI --server.port=$PORT --logger.level=error"]