from datetime import datetime, timezone
from langchain_core.tracers.base import AsyncBaseTracer
from langchain_core.tracers.schemas import Run
from agentscope.schema import Span, SpanStatus
from agentscope.sender import sender

class LangGraphAdapter(AsyncBaseTracer):
    def __init__(self, agent_id: str, trace_id: str, **kwargs):
        super().__init__(**kwargs)
        self.agent_id = agent_id
        self.trace_id = trace_id

    def _convert_run_to_span(self, run: Run) -> Span:
        span_type = "state_update"
        if run.run_type == "llm":
            span_type = "llm_call"
        elif run.run_type == "tool":
            span_type = "tool_call"
        elif run.run_type == "chain":
            span_type = "delegation"
            
        status = SpanStatus(status="success")
        if run.error:
            status = SpanStatus(status="error", exception_details=str(run.error))
            
        token_usage = None
        if run.run_type == "llm" and run.outputs:
            llm_output = run.outputs.get("llm_output", {})
            if isinstance(llm_output, dict) and "token_usage" in llm_output:
                tu = llm_output["token_usage"]
                token_usage = {
                    "prompt_tokens": tu.get("prompt_tokens", 0),
                    "completion_tokens": tu.get("completion_tokens", 0),
                    "total_tokens": tu.get("total_tokens", 0)
                }

        start_time = run.start_time
        if not start_time:
            start_time = datetime.now(timezone.utc)
            
        return Span(
            trace_id=self.trace_id,
            span_id=str(run.id),
            parent_span_id=str(run.parent_run_id) if run.parent_run_id else None,
            span_type=span_type,
            name=run.name,
            input=run.inputs,
            output=run.outputs,
            start_time=start_time,
            end_time=run.end_time,
            status=status,
            token_usage=token_usage,
            agent_id=self.agent_id
        )

    def _on_run_create(self, run: Run) -> None:
        """Process a run upon creation, sending an 'active' span live."""
        span = self._convert_run_to_span(run)
        sender.send(span)
        return None

    async def _on_run_update(self, run: Run) -> None:
        """Process a run upon completion, sending a 'complete' or 'error' span live."""
        span = self._convert_run_to_span(run)
        sender.send(span)

    async def _persist_run(self, run: Run) -> None:
        """Satisfy AsyncBaseTracer abc. We already emitted spans live via _on_run_update."""
        pass
