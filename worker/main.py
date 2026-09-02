import asyncio
import logging
from redis_client import redis_client
from anomaly_store import ensure_anomaly_index, persist_anomaly
from agentscope.schema import Span
from rules.engine import AnomalyEngine
from pydantic import ValidationError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Starting AgentScope Anomaly Worker...")
    engine = AnomalyEngine()
    await ensure_anomaly_index(redis_client)

    # Retrieve last processed ID to ensure no data loss (FR-4)
    last_id = await redis_client.get("agentscope:worker:last_id")
    if not last_id:
        last_id = "0-0"
        
    logger.info(f"Resuming from event ID: {last_id}")

    try:
        while True:
            try:
                # Block for up to 1000ms waiting for new events
                events = await redis_client.xread({"agentscope:events": last_id}, count=50, block=1000)
                if not events:
                    continue
                    
                for stream, messages in events:
                    for message_id, message in messages:
                        payload = message.get("payload")
                        if payload:
                            try:
                                span = Span.model_validate_json(payload)
                                # Evaluate anomalies
                                anomalies = engine.evaluate(span)
                                
                                for anomaly in anomalies:
                                    anomaly["is_anomaly"] = True
                                    # Persist the live stream record and its
                                    # per-trace history index atomically.
                                    await persist_anomaly(redis_client, anomaly)
                                    logger.warning(f"Anomaly detected: {anomaly['rule']} on span {anomaly['span_id']}")
                            except ValidationError as e:
                                logger.error(f"Failed to validate payload: {e}")
                            except Exception as e:
                                logger.error(f"Error evaluating span: {e}")

                        # Update last_id to ensure we don't re-process on restart
                        last_id = message_id
                        await redis_client.set("agentscope:worker:last_id", last_id)
                        
            except Exception as e:
                logger.error(f"Redis read error: {e}")
                await asyncio.sleep(1) # Backoff
                
    except asyncio.CancelledError:
        logger.info("Worker gracefully shutting down...")

if __name__ == "__main__":
    asyncio.run(main())
