import json
import logging
import re
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.redis_client import get_redis

logger = logging.getLogger(__name__)

router = APIRouter()

STREAM_ID_PATTERN = re.compile(r"^\d+-\d+$")


def _resume_cursor(value: str | None) -> str | None:
    """Accept only concrete Redis stream IDs from reconnecting clients."""
    return value if value and STREAM_ID_PATTERN.fullmatch(value) else None


async def _stream_tail(stream: str) -> str:
    """Resolve a fresh connection to a concrete durable stream position."""
    rows = await get_redis().xrevrange(stream, max="+", min="-", count=1)
    return str(rows[0][0]) if rows else "0-0"


def _with_stream_cursors(
    payload: str,
    stream: str,
    message_id: str,
    event_cursor: str,
    anomaly_cursor: str,
) -> str:
    """Add transport metadata without changing the canonical Span schema."""
    data = json.loads(payload)
    data["_agentscope_stream"] = stream
    data["_agentscope_stream_id"] = message_id
    data["_agentscope_event_cursor"] = event_cursor
    data["_agentscope_anomaly_cursor"] = anomaly_cursor
    return json.dumps(data)

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Fresh clients resolve both stream tails to concrete IDs. Every outgoing
    # frame then carries both cursors, so a reconnect can catch an anomaly even
    # when none had been observed before the disconnect.
    last_event_id = _resume_cursor(websocket.query_params.get("last_event_id"))
    last_anomaly_id = _resume_cursor(websocket.query_params.get("last_anomaly_id"))
    if last_event_id is None:
        last_event_id = await _stream_tail("agentscope:events")
    if last_anomaly_id is None:
        last_anomaly_id = await _stream_tail("agentscope:anomalies")
    try:
        while True:
            # Block for 1000ms waiting for new events
            # This allows the loop to periodically check for disconnects
            events = await get_redis().xread(
                {"agentscope:events": last_event_id, "agentscope:anomalies": last_anomaly_id},
                count=50, block=1000
            )
            if events:
                # events is a list of tuples: [(stream_name, [(msg_id, msg_dict), ...])]
                for stream, messages in events:
                    for message_id, message in messages:
                        payload = message.get("payload")
                        if payload:
                            if stream == "agentscope:anomalies":
                                last_anomaly_id = message_id
                                await websocket.send_text(
                                    _with_stream_cursors(
                                        payload, stream, message_id, last_event_id, last_anomaly_id
                                    )
                                )
                            else:
                                last_event_id = message_id
                                await websocket.send_text(
                                    _with_stream_cursors(
                                        payload, stream, message_id, last_event_id, last_anomaly_id
                                    )
                                )
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
