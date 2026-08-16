FROM python:3.11-slim

WORKDIR /app

COPY sdk /app/sdk
RUN pip install -e /app/sdk
RUN pip install redis httpx

COPY worker /app/worker
WORKDIR /app/worker
ENV PYTHONPATH=/app/worker

CMD ["python", "main.py"]
