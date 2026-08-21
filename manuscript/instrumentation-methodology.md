# Instrumentation Methodology

*Manuscript section — Track A draft (Week 11). Every number cites the CHANGELOG.md entry that produced it.*

AgentScope instruments multi-agent LLM systems through two integration paths that produce schema-identical spans:

1. **Zero-rewrite LangGraph adapter (Flow 1).** A subclass of `langchain_core.tracers.base.AsyncBaseTracer` is injected via `config["callbacks"]`; the monitored application's business logic is untouched — attaching observability is a two-line change at the invocation site.
2. **Decorator + client patching (Flow 2).** For custom agent loops or frameworks without a tracer interface, `@agentscope.trace` wraps arbitrary functions/tools as spans, and `agentscope.patch()` wraps the OpenAI and Anthropic Python clients so LLM calls are captured with normalized token usage.

Both paths emit the same Pydantic span model (`sdk/agentscope/schema.py`), enforced by a cross-path schema-identity test; no downstream component can tell which path produced a span.

## Delivery semantics

Spans are handed to an in-process asynchronous sender: a background task drains a queue and POSTs to the ingestion endpoint with bounded exponential backoff (3 retries). The send path never raises into the host process and never blocks it synchronously on network I/O; on unrecoverable failure a span is dropped with a local warning. This is the mechanism behind the resilience result: with the backend killed mid-run, the monitored agent completed 30/30 workloads with correct outputs and a clean exit (CHANGELOG [2026-08-22 00:45]).

Redaction is opt-in and client-side: when enabled, `input`/`output` are replaced with a placeholder *inside the SDK process* before serialization; wire-level tests confirm the raw payloads never leave the host (CHANGELOG [2026-08-22 00:45]).

## Measured overhead

Measured on the branching demo-agent workload, 30 paired interleaved runs with 5 discarded warmup pairs, no outlier removal (CHANGELOG [2026-08-21 23:30]; raw logs in `sdk/agentscope/benchmarks/results/`):

- **CPU-trivial demo workload** (~4.7ms per graph): +3.3ms mean absolute overhead (**+79.7% mean / +60.7% median relative**). The commonly-cited "<5%" target does not describe this regime — at sub-10ms workloads any instrumentation dominates. We report this number plainly.
- **LLM-bound workload** (same graph, 100ms simulated LLM latency per node, ~208ms per graph): +3.6ms mean absolute (**+1.76% mean and median relative**), meeting the <5% target on the workload class for which it was defined. The absolute cost of instrumentation is consistent (~3.3–3.6ms per graph invocation) across both regimes.

## Comparison point

Under identical workloads and an identical paired-run methodology, Arize Phoenix (OpenInference LangChain tracer, batch exporter to a local Phoenix instance, export verified) measured higher overhead than AgentScope on both workload classes: +201.7% vs. +93.1% (demo-as-is) and +2.6% vs. −0.5% mean (LLM-bound), n=15 per arm (CHANGELOG [2026-08-22 01:20]).

*Note: no claim is made here about observing an AWS-deployed AgentScope backend — cloud deployment is pending, and all measurements were taken against the local stack.*
