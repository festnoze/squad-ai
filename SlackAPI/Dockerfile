FROM python:3.12.1-slim

WORKDIR /
ENV PYTHONPATH=/src

ENV HOST_URI=0.0.0.0
ENV PORT=8301

ENV EXTERNAL_API_HOST="studi-website-rag-api"
ENV EXTERNAL_API_PORT="8281"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN rm -rf /outputs/logs/{*,.*}

EXPOSE $PORT

CMD ["sh", "-c", "python -m uvicorn src.api.startup:app --host $HOST_URI --port $PORT --log-level error"]