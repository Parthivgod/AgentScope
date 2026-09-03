# System Design

*Manuscript section — Track B draft (Week 11). Numbers appearing here are design parameters, not measured results; measured results appear in [Evaluation Results](evaluation-results.md) with per-claim citations.*

## Overview

AgentScope is a self-hosted observability platform for multi-agent LLM systems with three distinguishing capabilities delivered together: live (in-flight) execution-graph visualization, zero-rewrite instrumentation of LangGraph applications, and rule-based anomaly detection running concurrently with the observed workload. The system comprises four cooperating components — an instrumentation SDK embedded in the monitored agent, an ingestion backend, a Redis Streams event store, and an anomaly worker — plus a dashboard that renders the live graph and replays historical traces through a single rendering path.

## Architecture

The SDK captures spans inside the monitored agent and ships them asynchronously to a FastAPI ingestion endpoint fronted by Nginx. In framework-free Python applications, the `@trace` decorator and patched LLM clients share execution-scoped `contextvars`: a decorated delegation boundary pushes its agent identity, nested boundaries extend the ordered delegation chain, and patched calls inherit the active trace, parent span, owning agent, and zero-based hop number without requiring those values in business-function arguments. This closes the prior split in which decorated functions formed a hierarchy while patched LLM calls used independent default identities.

Validated spans are appended to a Redis Stream (`agentscope:events`), which is the single ordered log of the system. Two independent consumers read the same stream:

1. **The anomaly worker** evaluates six rule-based detectors (crashes, failure loops, timeouts, token spikes, message storms, delegation cycles) against the stream in strict arrival order and appends flagged anomalies to a second stream (`agentscope:anomalies`), checkpointing its read position so it can be killed and restarted without data loss.
2. **The WebSocket relay** multiplexes both streams to connected dashboards, delivering spans and anomaly flags as they occur.

Worker isolation is a load-bearing design property rather than an implementation convenience: ingestion, persistence, and live streaming continue unaffected while the worker is down, and the worker catches up from its checkpoint on restart.

### Read path

Historical replay is served by `GET /history/{trace_id}` and a trace listing by `GET /traces`. One Redis Lua operation atomically appends the canonical event, registers the trace, records the authoritative message ID, and maintains an ordered per-trace payload copy. Complete new traces are snapshotted with one transactional `LLEN`/`LRANGE`, avoiding one stream lookup per event. Data predating the payload index—and any deliberately detected partial index—uses the authoritative message-ID fallback, so an upgrade cannot silently truncate history. Per-trace anomaly indexes avoid global anomaly-stream scans after migration. Live and historical views share one graph-rendering component; cursor-based WebSocket reconnect replays retained event and anomaly entries after the last durable IDs before resuming live reads.

### Deployment

The reference deployment is a single docker-compose stack (Redis with append-only persistence, FastAPI backend, anomaly worker, Nginx) targeted at **AWS EC2** in the reference design; the actual cloud go-live is a separate, still-pending step, and all measurements reported in this manuscript were taken against the local docker-compose deployment. Nginx terminates TLS and enforces that ingestion requires a valid API key; the backend runs multiple stateless workers (all state lives in Redis) to reduce tail latency under concurrent load.

## Design principles

- **Observability must never risk availability.** Nothing in the SDK's send path may raise into the host agent or block synchronously on network I/O; delivery failures are logged locally and dropped after bounded retries.
- **Recovery is bounded and explicit.** Backend Redis clients health-check pooled connections and use bounded exponential retries. Cursor catch-up is guaranteed only for retained stream entries; trimming and invalid-cursor policy remain future work.
- **One schema, one rendering path.** A single Pydantic span model is shared by SDK, backend, worker, and dashboard; spans from all instrumentation paths are indistinguishable downstream.
- **Detection is not enforcement.** The system surfaces anomalies; it never kills, restarts, or otherwise acts on the monitored agent.
- **Client-side, opt-in redaction.** When enabled, sensitive span payloads are scrubbed inside the SDK process before anything leaves it. Immediately before scrubbing, the SDK computes a truncated HMAC-SHA256 progress fingerprint using a process-local secret that is never serialized or transmitted. The existing Failure Loops rule compares this fingerprint instead of the indistinguishable `[REDACTED]` placeholder, retaining same-versus-changed input discrimination without exposing the original value.
