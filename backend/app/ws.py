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
    
    # Start reading from the end of the stream
    last_id = "$"
    try:
        while True:
            # Block for 1000ms waiting for new events
            # This allows the loop to periodically check for disconnects
            events = await redis_client.xread({"agentscope:events": last_id}, count=50, block=1000)
            if events:
                # events is a list of tuples: [(stream_name, [(msg_id, msg_dict), ...])]
                for stream, messages in events:
                    for message_id, message in messages:
                        payload = message.get("payload")
                        if payload:
                            await websocket.send_text(payload)
                        last_id = message_id
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
