# AgentScope Backend & Infrastructure Guide

Backend (FastAPI), anomaly worker, and the local docker-compose deployment. Audience: contributors working on Track B components and anyone deploying the local stack.

## Architecture

```
SDK (monitored agent) ──HTTPS/HTTP──▶ Nginx (:80 plain / :8443 TLS)
                                        │  /ingest  /history  /traces  /ws
                                        ▼
                                    Backend (FastAPI, uvicorn, 4 workers)
                                        │
                                        ▼
                              Redis Streams (agentscope:events)
                                │                    │
                                │ XREAD              │ XREAD
                                ▼                    ▼
                          Anomaly Worker       WS relay (/ws) ──▶ Dashboard
                                │
                                ▼
                      Redis Stream (agentscope:anomalies) ──▶ WS relay ──▶ Dashboard
```

Key invariants (RULES.md §3): the worker is independently killable — ingestion never depends on it (#6); events are processed in strict arrival order (#4); the schema lives only in `sdk/agentscope/schema.py` (#2, Decision 2).

## Components

- `backend/app/ingest.py` — `POST /ingest` (API-key auth, FR-7); one Lua operation appends to `agentscope:events`, registers the trace, records the Redis message ID, and stores the ordered per-trace payload copy.
- `backend/app/history.py` — `GET /history/{trace_id}` snapshots a complete payload index with one transactional `LLEN`/`LRANGE`. Legacy or partially indexed traces use authoritative Redis message-ID ordering. `GET /traces` returns the most-recent-first trace list.
- `backend/app/ws.py` — `GET /ws` WebSocket relay multiplexing the events and anomalies streams; optional event/anomaly cursors provide retained-stream reconnect catch-up.
- `backend/app/redis_client.py` — shared async Redis clients with one-second health checks and bounded exponential reconnect retries.
- `worker/main.py` — independent process; XREADs `agentscope:events`, evaluates the six rule-based detectors (`worker/rules/`), writes anomalies to `agentscope:anomalies`; checkpoint in `agentscope:worker:last_id` so restarts lose nothing (FR-4).
- `infra/docker-compose.yml` — redis (AOF persistence), backend (4 workers), worker, nginx.
- `infra/nginx/nginx.conf` — reverse proxy; terminates TLS on :8443.

## Running the stack

```powershell
cd infra
$env:AGENTSCOPE_API_KEY = "<your-key>"
docker compose up --build -d
docker compose ps   # redis, backend, worker, nginx all Up
```

TLS (local, self-signed — generate once; certs are gitignored):

```powershell
openssl req -x509 -nodes -newkey rsa:2048 -days 365    -keyout nginx/certs/server.key -out nginx/certs/server.crt    -subj "//CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

Endpoints: `http://localhost/{ingest,traces,history,ws}` and the same over `https://localhost:8443` (self-signed).

## Testing & operational checks

- Unit/integration: `cd backend; python -m pytest tests` (18 tests; uses a local Redis on `localhost:6379` — point `REDIS_URL` elsewhere to avoid touching a running stack's data).
- End-to-end smoke: `python scripts/smoke-test.py` (requires an externally managed Redis and free port 8000, uses isolated DB 14, and starts its own backend and worker; do not run it over an already running full stack).
- Load testing: `infra/loadtest/` — `locustfile.py` (mixed traffic), `locustfile_ingest_only.py`, and `event_latency_probe.py` (event-to-dashboard latency; run alongside background load).
- Resilience: `scripts/resilience-stack.py {worker-kill|redis-restart|slow-ws}`.
- Backend-kill from the SDK side: `scripts/resilience-backend-kill.py` (Track A).

## Known operational notes

- `/traces` may briefly list a trace whose events were externally flushed (the read index outlives the stream); `/history` falls back and 404s correctly. Logged in `docs/future-work.md`.
- Redis requests use bounded reconnect retries and stale pooled connections are health-checked. The latest ready-state restart run retained 40/40 bounded test events and recovered in about one second with no post-restart transient failures; calls made while Redis itself is unavailable may still fail, and non-idempotent retry ambiguity is not claimed away.
- The ordered payload copy improves history latency at the cost of additional Redis memory. Complete new traces use it; legacy/partial traces remain on the message-ID fallback to prevent truncation.
