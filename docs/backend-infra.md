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

- `backend/app/ingest.py` — `POST /ingest` (API-key auth, FR-7; writes to the `agentscope:events` stream and maintains the per-trace read index `agentscope:traces` ZSET + `agentscope:trace:<id>` lists; index maintenance is fail-silent).
- `backend/app/history.py` — `GET /history/{trace_id}` (spans in arrival order; O(trace) via the index, full-scan fallback that rebuilds the index) and `GET /traces` (most-recent-first trace list).
- `backend/app/ws.py` — `GET /ws` WebSocket relay multiplexing the events and anomalies streams.
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

- Unit/integration: `cd backend; python -m pytest tests` (9 tests; uses a local Redis on `localhost:6379` — point `REDIS_URL` elsewhere to avoid touching a running stack's data).
- End-to-end smoke: `python scripts/smoke-test.py` (ingest → Redis → WS relay → anomaly flag).
- Load testing: `infra/loadtest/` — `locustfile.py` (mixed traffic), `locustfile_ingest_only.py`, and `event_latency_probe.py` (event-to-dashboard latency; run alongside background load).
- Resilience: `scripts/resilience-stack.py {worker-kill|redis-restart|slow-ws}`.
- Backend-kill from the SDK side: `scripts/resilience-backend-kill.py` (Track A).

## Known operational notes

- `/traces` may briefly list a trace whose events were externally flushed (the read index outlives the stream); `/history` falls back and 404s correctly. Logged in `docs/future-work.md`.
- Transient 5xx on `/ingest` during a full Redis restart is expected (Redis is the store); accepted events are never lost (AOF) and the backend self-heals its connection pool within seconds.
