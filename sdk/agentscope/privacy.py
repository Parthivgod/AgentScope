"""Client-local privacy helpers for redaction-safe progress comparison."""

import hashlib
import hmac
import json
import secrets
from typing import Any, Optional


# Process-local by design: never serialized, logged, or sent to the backend.
_HMAC_KEY = secrets.token_bytes(32)
_FINGERPRINT_HEX_LENGTH = 32  # 128 bits after truncation


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=repr,
    ).encode("utf-8")


def compute_progress_fingerprint(value: Any) -> Optional[str]:
    """Return a stable, process-local HMAC for non-null progress/input data."""
    if value is None:
        return None
    digest = hmac.new(_HMAC_KEY, _canonical_bytes(value), hashlib.sha256).hexdigest()
    return digest[:_FINGERPRINT_HEX_LENGTH]
