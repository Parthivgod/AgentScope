FROM python:3.11-slim@sha256:1042b61448fef4ba92d16a8c7eb4996d027568ce64792a7877fd88511e0af7c6

WORKDIR /app

COPY sdk /app/sdk
COPY constraints /app/constraints
RUN pip install -c /app/constraints/evaluation.txt -e /app/sdk
COPY backend/requirements.txt /app/backend-requirements.txt
RUN pip install -c /app/constraints/evaluation.txt -r /app/backend-requirements.txt

COPY backend /app/backend
WORKDIR /app/backend
ENV PYTHONPATH=/app/backend

# Multiple workers: the app is stateless (all state lives in Redis), so extra
# workers reduce tail latency under concurrent load (Week 9 load-test finding).
CMD ["uvicorn", "app.ingest:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
