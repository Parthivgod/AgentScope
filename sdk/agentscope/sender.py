import asyncio
import os
import httpx
import logging
from typing import Optional
from agentscope.schema import Span
from agentscope.config import AGENTSCOPE_INGEST_URL, AGENTSCOPE_API_KEY, is_redaction_enabled

logger = logging.getLogger(__name__)

class AsyncEventSender:
    def __init__(self, max_retries: int = 3, initial_backoff: float = 0.5, backoff_factor: float = 2.0):
        self.queue = asyncio.Queue()
        self.client = httpx.AsyncClient(timeout=5.0)
        self.task: Optional[asyncio.Task] = None
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.backoff_factor = backoff_factor

    def _start_task_if_needed(self):
        if self.task is None or self.task.done():
            try:
                loop = asyncio.get_running_loop()
                self.task = loop.create_task(self._worker())
            except RuntimeError:
                # No running event loop
                pass

    async def _worker(self):
        while True:
            span = await self.queue.get()
            try:
                # Client-side redaction guarantee (Decision #4 / NFR 9.4)
                if is_redaction_enabled():
                    span = span.model_copy(update={"input": "[REDACTED]", "output": "[REDACTED]"})

                headers = {}
                api_key = os.environ.get("AGENTSCOPE_API_KEY") or AGENTSCOPE_API_KEY
                ingest_url = os.environ.get("AGENTSCOPE_INGEST_URL") or AGENTSCOPE_INGEST_URL
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"

                payload = span.model_dump(mode="json")

                # Bounded exponential backoff retry loop
                for attempt in range(self.max_retries + 1):
                    try:
                        res = await self.client.post(ingest_url, json=payload, headers=headers)
                        if res.status_code < 400:
                            # Success
                            break
                        elif 400 <= res.status_code < 500:
                            # Non-transient client error (e.g. 401 Unauthorized) -> do not retry
                            logger.warning(
                                f"AgentScope post failed with client error {res.status_code} for span {span.span_id}. Dropping span."
                            )
                            break
                        else:
                            # Server error (5xx) -> transient failure, candidate for retry
                            res.raise_for_status()
                    except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                        if attempt < self.max_retries:
                            backoff = self.initial_backoff * (self.backoff_factor ** attempt)
                            logger.warning(
                                f"AgentScope transient send failure (attempt {attempt + 1}/{self.max_retries + 1}) for span {span.span_id}: {exc}. Retrying in {backoff:.2f}s..."
                            )
                            await asyncio.sleep(backoff)
                        else:
                            logger.warning(
                                f"AgentScope send retries exhausted for span {span.span_id} after {self.max_retries + 1} attempts: {exc}"
                            )
            except Exception as e:
                # Fail silent guarantee (RULES.md §3.1, §3.2)
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
