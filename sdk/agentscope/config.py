import os

AGENTSCOPE_API_KEY = os.environ.get("AGENTSCOPE_API_KEY")
AGENTSCOPE_INGEST_URL = os.environ.get("AGENTSCOPE_INGEST_URL", "http://localhost:8000/ingest")
AGENTSCOPE_REDACT_ENABLED = os.environ.get("AGENTSCOPE_REDACT_ENABLED", "false").lower() == "true"
