FROM python:3.11-slim@sha256:1042b61448fef4ba92d16a8c7eb4996d027568ce64792a7877fd88511e0af7c6

WORKDIR /app

COPY sdk /app/sdk
COPY constraints /app/constraints
RUN pip install -c /app/constraints/evaluation.txt -e /app/sdk
COPY worker/requirements.txt /app/worker-requirements.txt
RUN pip install -c /app/constraints/evaluation.txt -r /app/worker-requirements.txt

COPY worker /app/worker
WORKDIR /app/worker
ENV PYTHONPATH=/app/worker

CMD ["python", "main.py"]
