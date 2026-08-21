# System Design

*Manuscript section — Track B draft (Week 11). Numbers appearing here are design parameters, not measured results; measured results appear in [Evaluation Results](evaluation-results.md) with per-claim citations.*

## Overview

AgentScope is a self-hosted observability platform for multi-agent LLM systems with three distinguishing capabilities delivered together: live (in-flight) execution-graph visualization, zero-rewrite instrumentation of LangGraph applications, and rule-based anomaly detection running concurrently with the observed workload. The system comprises four cooperating components — an instrumentation SDK embedded in the monitored agent, an ingestion backend, a Redis Streams event store, and an anomaly worker — plus a dashboard that renders the live graph and replays historical traces through a single rendering path.

## Architecture

The SDK captures spans inside the monitored agent and ships them asynchronously to a FastAPI ingestion endpoint fronted by Nginx. Validated spans are appended to a Redis Stream (`agentscope:events`), which is the single ordered log of the system. Two independent consumers read the same stream:

1. **The anomaly worker** evaluates six rule-based detectors (crashes, failure loops, timeouts, token spikes, message storms, delegation cycles) against the stream in strict arrival order and appends flagged anomalies to a second stream (`agentscope:anomalies`), checkpointing its read position so it can be killed and restarted without data loss.
2. **The WebSocket relay** multiplexes both streams to connected dashboards, delivering spans and anomaly flags as they occur.

Worker isolation is a load-bearing design property rather than an implementation convenience: ingestion, persistence, and live streaming continue unaffected while the worker is down, and the worker catches up from its checkpoint on restart.

### Read path

Historical replay is served by `GET /history/{trace_id}` and a trace listing by `GET /traces`. Ingestion maintains a per-trace read index (a timestamp-scored ZSET of trace IDs plus per-trace message-ID lists), so replay reads are proportional to the trace size rather than the total event volume; a full-scan fallback preserves correctness for data predating the index and rebuilds it lazily. Live and historical views deliberately share one graph-rendering component in the dashboard — the only difference is the event source — which removes an entire class of live/replay divergence defects.

### Deployment

The reference deployment is a single docker-compose stack (Redis with append-only persistence, FastAPI backend, anomaly worker, Nginx) targeted at **AWS EC2** in the reference design; the actual cloud go-live is a separate, still-pending step, and all measurements reported in this manuscript were taken against the local docker-compose deployment. Nginx terminates TLS and enforces that ingestion requires a valid API key; the backend runs multiple stateless workers (all state lives in Redis) to reduce tail latency under concurrent load.

## Design principles

- **Observability must never risk availability.** Nothing in the SDK's send path may raise into the host agent or block synchronously on network I/O; delivery failures are logged locally and dropped after bounded retries.
- **One schema, one rendering path.** A single Pydantic span model is shared by SDK, backend, worker, and dashboard; spans from all instrumentation paths are indistinguishable downstream.
- **Detection is not enforcement.** The system surfaces anomalies; it never kills, restarts, or otherwise acts on the monitored agent.
- **Client-side, opt-in redaction.** When enabled, sensitive span payloads are scrubbed inside the SDK process before anything leaves it.
