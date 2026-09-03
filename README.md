# AgentScope

AgentScope is a local-first observability and anomaly detection tool for autonomous agents: **live** execution-graph visualization, **zero-rewrite** instrumentation, and **rule-based anomaly detection** — delivered as a single docker-compose stack you can self-host.

For the complete architecture, technology stack, operating model, diagrams, and consolidated evaluation tables, see [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md).

- **Monitored agent** — your LangGraph or custom Python agent, instrumented by the AgentScope SDK (`sdk/`)
- **Ingestion + storage** — FastAPI backend behind Nginx, Redis Streams as the ordered event log (`backend/`, `infra/`)
- **Anomaly worker** — six rule-based detectors, independently killable (`worker/`)
- **Dashboard** — live graph + historical replay through one rendering path (`dashboard/`)

---

## 1. Quick Start (local stack)

### 1.1 Preflight
Docker Desktop running, port 8000 free:
- **Windows**: `.\scripts\dev-preflight.ps1`
- **Linux/Mac**: `./scripts/dev-preflight.sh`

### 1.2 Infrastructure + backend (full compose stack)
```powershell
cd infra
$env:AGENTSCOPE_API_KEY = "<your-key>"   # local default is "test-key"
docker compose up --build -d
docker compose ps   # redis, backend, worker, nginx all Up
```
Endpoints: `http://localhost/{ingest,traces,history,ws}` and the same over `https://localhost:8443` (self-signed TLS).

TLS cert (local, self-signed — generate once; certs are gitignored):
```powershell
openssl req -x509 -nodes -newkey rsa:2048 -days 365 -keyout nginx/certs/server.key -out nginx/certs/server.crt -subj "//CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

<details><summary>Running the backend outside Docker (optional)</summary>

```powershell
cd backend
$env:AGENTSCOPE_API_KEY = "test-key"
uvicorn app.ingest:app --host 0.0.0.0 --port 8000
```
</details>

### 1.3 Dashboard
```powershell
cd dashboard
npm install
npm run dev   # http://localhost:5173 (dev server proxies API/WS to Nginx)
```

- **Live mode** (default): every span streamed while the tab is open becomes a node; parent links become edges; dagre lays out the hierarchy. Node states: ⟳ active, ✓ complete, ✖ error, ⚠ anomalous (amber dashed border). Click a node (or Tab + Enter) to open the InspectPanel; Escape closes it.
- **Historical Replay**: trace dropdown lists real traces from `GET /traces`; same rendering component as live. Failed fetches show an explicit error banner.
- 🔒 **Redacted Data** badge appears when any visible span carries `[REDACTED]` payloads.

---

## 2. Instrumenting your agent (SDK)

Two integration paths, both emitting schema-identical spans, delivered asynchronously and fail-silent (telemetry can never block or crash the monitored agent):

- **Flow 1 — LangGraph adapter (zero rewrite):** attach `LangGraphAdapter` via `config["callbacks"]` — no changes to agent business logic. Optional `agent_id_by_run` mapping gives each agent/node in a multi-agent graph its own span identity (recommended; it makes delegation-cycle detection meaningful).
- **Flow 2 — decorator + patching:** `@agentscope.trace` for custom functions/tools; `agentscope.patch()` for OpenAI and Anthropic clients.

```powershell
pip install -e ./sdk               # base (Flow 2)
pip install -e "./sdk[langgraph]"  # + LangGraph adapter (Flow 1)
```

Environment variables:
```powershell
$env:AGENTSCOPE_API_KEY = "your-secret-api-key"
$env:AGENTSCOPE_INGEST_URL = "http://localhost:8000/ingest"   # default
$env:AGENTSCOPE_REDACT_ENABLED = "false"   # "true" = client-side redaction of input/output
```

Verify spans are arriving:
```powershell
curl http://localhost/traces
curl http://localhost/history/<trace_id>
```

Flow 1 in two lines (the whole instrumentation surface):
```python
from agentscope import LangGraphAdapter
adapter = LangGraphAdapter(agent_id="my-agent", trace_id="trace-1")
result = await graph.ainvoke(state, config={"callbacks": [adapter]})
```

**Measured, bounded evidence:** backend termination left the monitored application successful in 30/30 fault-injection workloads; redaction excluded raw sentinel payloads from the captured wire object; the latest three-process 100ms/node comparison measured 4.81% mean overhead (95% t interval 1.28–8.33) and therefore does not support an unconditional <5% claim. See [Evaluation Results](manuscript/evaluation-results.md).

---

## 3. Demo agents (`examples/`)

### 3.1 `langgraph_demo_agent` — Flow 1, no LLM calls
Linear 3-node pipeline (`linear_agent.py`) and a branching router graph (`branching_agent.py`). Free to run repeatedly.
```powershell
cd examples/langgraph_demo_agent
pip install -r requirements.txt
$env:AGENTSCOPE_API_KEY = "test-key"
python main.py
```

### 3.2 `custom_demo_agent` — Flow 2, no LLM calls
`@agentscope.trace` + `patch(openai)` on a custom agent loop. Tests: `python -m pytest test_demo_e2e.py`.

### 3.3 `support_triage_demo` — multi-agent with REAL LLM calls (GPT-OSS 120B on Bedrock)
A supervisor/router + billing/technical/account specialists + response composer. **Real LLM calls do the classification, specialist reasoning, and drafting**; local synthetic tools; 4 poison tickets deterministically trigger 4 different anomaly rules and 4 happy-path tickets are the false-positive check. Demo-scripted sequence: `examples/support_triage_demo/RUN_ORDER.md`.

Requirements: AWS credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` — us-east-1) and `pip install -r requirements.txt` (langchain-aws, boto3). Full 8-ticket run ≈ a few cents; hard per-run ceiling of 15 LLM calls per ticket as the cost safety net.

```powershell
cd examples/support_triage_demo
$env:AWS_ACCESS_KEY_ID = "..."
$env:AWS_SECRET_ACCESS_KEY = "..."
$env:AWS_REGION = "us-east-1"
$env:AGENTSCOPE_API_KEY = "test-key"
$env:AGENTSCOPE_INGEST_URL = "http://localhost:8000/ingest"

python main.py happy   # 4 normal tickets — zero anomalies expected
python main.py poison  # DELEGATION-CYCLE / FAIL-LOOP / TIMEOUT / TOKEN-SPIKE
python main.py all
```

| Ticket | Behavior | Rule |
|---|---|---|
| `HAPPY-*` (4) | Normal routing and resolution | none (false-positive check) |
| `DELEGATION-CYCLE-001` | Billing ↔ Technical each disown the ticket; routing bounces back to a visited agent | `delegation_cycles` |
| `FAIL-LOOP-002` | Account store returns ambiguous records; agent retries the identical lookup 5× | `failure_loops` |
| `TIMEOUT-003` | Diagnostic tool hangs 31s (~35s total run) | `timeouts` |
| `TOKEN-SPIKE-004` | ~100KB ticket history pushes one composer call >8k tokens | `token_spikes` |

The zero-rewrite point: `agent.py` contains the entire multi-agent system and imports nothing from AgentScope — observability is attached only in `main.py`.

---

## 4. Testing & operational checks

```powershell
python -m pytest sdk/tests                 # 30 tests
Push-Location backend; python -m pytest tests; Pop-Location  # 18 tests
python -m pytest worker/tests              # 4 tests
docker compose -f infra/docker-compose.yml up -d redis
python scripts/smoke-test.py               # requires port 8000 free; isolated DB 14
```

- **Load testing** (`infra/loadtest/`): `locustfile.py` (mixed traffic through Nginx), `locustfile_ingest_only.py`, `event_latency_probe.py` (event-to-dashboard latency; run alongside background load).
- **Resilience**: `python scripts/resilience-stack.py {worker-kill|redis-restart|slow-ws}`; backend-kill from the SDK side: `python scripts/resilience-backend-kill.py`.
- **Benchmarks/evaluation**: `scripts/evaluation/` contains repeatable latency, aggregation, three-way, convergence, privacy, and anomaly protocols. The latest results are under `manuscript/evaluation-artifacts/2026-09-03-history-payload-index/` and `2026-09-02-replicated/`.
- **Dashboard checks** (from `dashboard/`): `node scripts/a11y-scan.mjs`, `node scripts/keyboard-nav-test.mjs`, `node scripts/escape-close-test.mjs`, and `node scripts/demo-readiness-test.mjs`.

Operational notes: Redis clients use bounded exponential reconnect retries and health checks. In the latest ready-state restart test, all 20 pre-restart and 20 post-restart events were retained with no post-restart transient failures; requests made while Redis itself is unavailable can still fail. `/traces` may briefly list a trace whose events were externally flushed.

---

## 5. Project layout

```
sdk/        Instrumentation SDK (schema, adapter, decorator, patch, sender, benchmarks)
backend/    FastAPI ingest + history/traces + WS relay
worker/     Anomaly worker: 6 rule-based detectors (crashes, failure loops, timeouts,
            token spikes, message storms, delegation cycles)
dashboard/  Vite + React + React Flow graph UI (live + replay, dagre layout)
infra/      docker-compose stack, Nginx (TLS on :8443), load tests
examples/   langgraph_demo_agent, custom_demo_agent, support_triage_demo
docs/       Deep guides: sdk-quickstart, backend-infra, dashboard, demo-script,
            usability-test-prep, future-work
manuscript/ Working manuscript sections (System Design, Evaluation Results,
            Instrumentation Methodology) with per-claim citations
PROJECT_OVERVIEW.md  Consolidated architecture, stack, operation, and results
```

## 6. Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for required git configuration before committing. Read [RULES.md](RULES.md) before making any code changes — it encodes locked decisions and architectural invariants (fail-silent SDK, schema identity across paths, worker isolation, detection-not-enforcement, no unresolved mocks at checkpoints, no unevidenced performance claims).
