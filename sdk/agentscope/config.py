import os

_redact_enabled_override = None

def is_redaction_enabled() -> bool:
    """
    Returns True if client-side redaction is enabled (Decision #4 / NFR 9.4).
    Default behavior is full capture (False) unless AGENTSCOPE_REDACT_ENABLED=true
    or set_redaction_enabled(True) is called.
    """
    global _redact_enabled_override
    if _redact_enabled_override is not None:
        return _redact_enabled_override
    env_val = os.environ.get("AGENTSCOPE_REDACT_ENABLED", "false").strip().lower()
    return env_val in ("true", "1", "yes")

def set_redaction_enabled(enabled: bool) -> None:
    """Programmatically sets the client-side redaction toggle."""
    global _redact_enabled_override
    _redact_enabled_override = enabled

def reset_redaction_config() -> None:
    """Resets any programmatic redaction override."""
    global _redact_enabled_override
    _redact_enabled_override = None

AGENTSCOPE_API_KEY = os.environ.get("AGENTSCOPE_API_KEY")
AGENTSCOPE_INGEST_URL = os.environ.get("AGENTSCOPE_INGEST_URL", "http://localhost:8000/ingest")
AGENTSCOPE_REDACT_ENABLED = is_redaction_enabled()
