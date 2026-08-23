from datetime import datetime, timezone
from langchain_core.tracers.base import AsyncBaseTracer
from langchain_core.tracers.schemas import Run
from agentscope.schema import Span, SpanStatus
from agentscope.sender import sender

class LangGraphAdapter(AsyncBaseTracer):
    """
    LangChain / LangGraph callback tracer adapter for zero-rewrite instrumentation (Flow 1 integration).
    
    Subclasses `AsyncBaseTracer` to observe LangGraph node/chain/llm runs and automatically convert
    them into AgentScope `Span` schema events. Injected via `config={"callbacks": [adapter]}` or
    attached directly to compiled graphs. Emits live 'active' spans on start and 'complete'/'error'
    spans on end.
    
    Args:
        agent_id: Agent identifier assigned to generated spans.
        trace_id: Trace identifier associated with the full run.
        agent_id_by_run: Optional mapping (dict or callable) from run name to
            a per-run agent identifier. In a multi-agent graph, assigning each
            agent/node its own identity makes anomaly rules meaningful (e.g.
            delegation-cycle detection compares agent_ids along the parent
            chain; a single shared agent_id trivially "cycles" on any nested
            run). Runs not present in the mapping fall back to `agent_id`.
            Additive option — default behavior is unchanged.
    """
    def __init__(self, agent_id: str, trace_id: str, agent_id_by_run=None, **kwargs):
        super().__init__(**kwargs)
        self.agent_id = agent_id
        self.trace_id = trace_id
        self.agent_id_by_run = agent_id_by_run

    def _resolve_agent_id(self, run_name: str) -> str:
        if self.agent_id_by_run is None:
            return self.agent_id
        if callable(self.agent_id_by_run):
            return self.agent_id_by_run(run_name) or self.agent_id
        return self.agent_id_by_run.get(run_name, self.agent_id)

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
            tu = None
            # OpenAI-style chat models expose usage in llm_output.token_usage;
            # Bedrock (ChatBedrockConverse) serializes it on the generation's
            # message kwargs instead. Try both, fail-silent.
            llm_output = run.outputs.get("llm_output", {})
            if isinstance(llm_output, dict) and isinstance(llm_output.get("token_usage"), dict):
                tu = llm_output["token_usage"]
            else:
                try:
                    generations = run.outputs.get("generations") or []
                    kw = generations[0][0]["message"]["kwargs"]
                    if isinstance(kw.get("usage_metadata"), dict):
                        tu = {
                            "prompt_tokens": kw["usage_metadata"].get("input_tokens"),
                            "completion_tokens": kw["usage_metadata"].get("output_tokens"),
                            "total_tokens": kw["usage_metadata"].get("total_tokens"),
                        }
                except (IndexError, KeyError, TypeError):
                    tu = None
            if isinstance(tu, dict):
                prompt_tok = tu.get("prompt_tokens", 0) or 0
                comp_tok = tu.get("completion_tokens", 0) or 0
                tot_tok = tu.get("total_tokens", 0) or (prompt_tok + comp_tok)
                token_usage = {
                    "prompt_tokens": int(prompt_tok) if isinstance(prompt_tok, (int, float, str)) and str(prompt_tok).isdigit() else 0,
                    "completion_tokens": int(comp_tok) if isinstance(comp_tok, (int, float, str)) and str(comp_tok).isdigit() else 0,
                    "total_tokens": int(tot_tok) if isinstance(tot_tok, (int, float, str)) and str(tot_tok).isdigit() else 0
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
            agent_id=self._resolve_agent_id(run.name)
        )

    async def _on_run_create(self, run: Run) -> None:
        """Process a run upon creation, sending an 'active' span live."""
        span = self._convert_run_to_span(run)
        sender.send(span)

    async def _on_run_update(self, run: Run) -> None:
        """Process a run upon completion, sending a 'complete' or 'error' span live."""
        span = self._convert_run_to_span(run)
        sender.send(span)

    async def _persist_run(self, run: Run) -> None:
        """Satisfy AsyncBaseTracer abc. We already emitted spans live via _on_run_update."""
        pass
