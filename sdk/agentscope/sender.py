import asyncio
import httpx
import logging
from typing import Optional
from agentscope.schema import Span
from agentscope.config import AGENTSCOPE_INGEST_URL, AGENTSCOPE_API_KEY

logger = logging.getLogger(__name__)

class AsyncEventSender:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.client = httpx.AsyncClient(timeout=5.0)
        self.task: Optional[asyncio.Task] = None

    def _start_task_if_needed(self):
        if self.task is None or self.task.done():
            try:
                loop = asyncio.get_running_loop()
                self.task = loop.create_task(self._worker())
            except RuntimeError:
                # No running event loop
                pass

    async def _worker(self):
        headers = {}
        if AGENTSCOPE_API_KEY:
            headers["Authorization"] = f"Bearer {AGENTSCOPE_API_KEY}"
            
        while True:
            span = await self.queue.get()
            try:
                # Convert datetime to isoformat and dump as json
                payload = span.model_dump(mode="json")
                res = await self.client.post(AGENTSCOPE_INGEST_URL, json=payload, headers=headers)
                res.raise_for_status()
            except Exception as e:
                # Fail silent (RULES.md §3)
                logger.warning(f"AgentScope failed to send span {span.span_id}: {e}")
            finally:
                self.queue.task_done()

    def send(self, span: Span):
        self._start_task_if_needed()
        try:
            self.queue.put_nowait(span)
        except Exception as e:
            logger.warning(f"AgentScope failed to enqueue span {span.span_id}: {e}")

# Singleton instance
sender = AsyncEventSender()
