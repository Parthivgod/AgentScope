FROM python:3.11-slim

WORKDIR /app

COPY sdk /app/sdk
RUN pip install -e /app/sdk
RUN pip install fastapi "uvicorn[standard]" redis

COPY backend /app/backend
WORKDIR /app/backend
ENV PYTHONPATH=/app/backend

CMD ["uvicorn", "app.ingest:app", "--host", "0.0.0.0", "--port", "8000"]
