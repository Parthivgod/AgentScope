import json
import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.redis_client import redis_client

logger = logging.getLogger(__name__)

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Start reading from the end of both streams
    last_event_id = "$"
    last_anomaly_id = "$"
    try:
        while True:
            # Block for 1000ms waiting for new events
            # This allows the loop to periodically check for disconnects
            events = await redis_client.xread(
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
                                # Track C expects anomaly flags flowing here.
                                # Send as raw JSON just like events.
                                await websocket.send_text(payload)
                                last_anomaly_id = message_id
                            else:
                                await websocket.send_text(payload)
                                last_event_id = message_id
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
