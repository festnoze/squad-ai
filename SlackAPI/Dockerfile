FROM python:3.12.1-slim

WORKDIR /

COPY requirements.txt .
#RUN pip install --no-cache-dir requests python-dotenv uvicorn fastapi slack-sdk
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/src
ENV PORT=8301
ENV HOST_URI=0.0.0.0

EXPOSE $PORT

CMD ["sh", "-c", "python -m uvicorn src.slack_controller:app --host $HOST_URI --port $PORT --log-level error"]