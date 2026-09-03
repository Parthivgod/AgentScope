# Instrumentation Methodology

*Manuscript section synchronized with the latest replicated evidence through 2026-09-03.*

AgentScope instruments multi-agent LLM systems through two integration paths that produce schema-identical spans:

1. **Zero-rewrite LangGraph adapter (Flow 1).** A subclass of `langchain_core.tracers.base.AsyncBaseTracer` is injected via `config["callbacks"]`; the monitored application's business logic is untouched — attaching observability is a two-line change at the invocation site.
2. **Decorator + client patching (Flow 2).** For custom agent loops or frameworks without a tracer interface, `@agentscope.trace` wraps arbitrary functions/tools as spans, and `agentscope.patch()` wraps the OpenAI and Anthropic Python clients so LLM calls are captured with normalized token usage.

Both paths emit the same Pydantic span model (`sdk/agentscope/schema.py`), enforced by a cross-path schema-identity test; no downstream component can tell which path produced a span.

## Delivery semantics

Spans are handed to an in-process asynchronous sender: a background task drains a queue and POSTs to the ingestion endpoint with bounded exponential backoff (3 retries). The send path never raises into the host process and never blocks it synchronously on network I/O; on unrecoverable failure a span is dropped with a local warning. This is the mechanism behind the resilience result: with the backend killed mid-run, the monitored agent completed 30/30 workloads with correct outputs and a clean exit (CHANGELOG [2026-08-22 00:45]).

Redaction is opt-in and client-side: when enabled, `input`/`output` are replaced with a placeholder *inside the SDK process* before serialization; wire-level tests confirm the raw payloads never leave the host (CHANGELOG [2026-08-22 00:45]).

## Measured overhead

The latest study used three fresh AgentScope processes/storage stacks, 30 measured baseline/instrumented pairs per workload and process after five warm-ups, no outlier removal, and 210/210 verified traces. CPU-trivial mean overhead was 68.92% (95% t interval across processes 39.16–98.69) with a 2.230 ms mean absolute delta. On the 100 ms/node workload it was 4.81% (1.28–8.33) with a 10.155 ms mean delta. Because the latter interval crosses 5%, this evidence does not support an unconditional “<5%” claim. CPU-trivial percentages are dominated by their millisecond baseline. Raw data and versions are in `evaluation-artifacts/2026-09-02-replicated/`.

## Comparison point

The replicated comparison used the same workload/protocol for AgentScope, Langfuse, and Phoenix. On the 100 ms/node workload, mean overhead was 4.81%, 5.24%, and 6.56%, respectively, but the low-powered three-process intervals overlap substantially. The result reports bounded local overhead and verified ingestion, not a reliable ranking or broader diagnostic superiority.

*Note: no claim is made here about observing an AWS-deployed AgentScope backend — cloud deployment is pending, and all measurements were taken against the local stack.*
