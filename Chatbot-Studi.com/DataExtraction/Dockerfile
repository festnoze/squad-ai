FROM python:3.12.1-slim

WORKDIR /
ENV PYTHONPATH=/src
ENV PORT=8281
ENV HOST_URI=0.0.0.0

COPY wheels/ /wheels/
COPY requirements_common.txt .

# RUN pip install /wheels/*.whl
# RUN pip install --no-cache-dir -r requirements_common.txt
COPY requirements.txt .
COPY requirements_docker.txt .
RUN pip install  --no-cache-dir -r requirements_docker.txt

COPY . .
RUN chmod 777 src/database_conversations/conversation_database.db
RUN rm -rf /outputs/logs/{*,.*}

EXPOSE $PORT

CMD ["sh", "-c", "python -m uvicorn src.api.startup:app --host $HOST_URI --port $PORT --log-level error"]