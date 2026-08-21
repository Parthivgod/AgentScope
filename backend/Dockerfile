FROM python:3.11-slim

WORKDIR /app

COPY sdk /app/sdk
RUN pip install -e /app/sdk
RUN pip install fastapi "uvicorn[standard]" redis

COPY backend /app/backend
WORKDIR /app/backend
ENV PYTHONPATH=/app/backend

# Multiple workers: the app is stateless (all state lives in Redis), so extra
# workers reduce tail latency under concurrent load (Week 9 load-test finding).
CMD ["uvicorn", "app.ingest:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
