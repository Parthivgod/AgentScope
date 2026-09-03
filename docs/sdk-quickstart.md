# AgentScope SDK Quickstart

Welcome to AgentScope! This quickstart covers setting up AgentScope SDK in your Python project within five minutes.

---

## 1. Installation

Install the AgentScope SDK directly via `pip`:

```powershell
pip install agentscope-sdk
```

Or for local development inside the monorepo:

```powershell
pip install -e ./sdk
```

---

## 2. Environment Variables

Configure the SDK using environment variables (or fall back to defaults):

```powershell
# AgentScope Ingestion Endpoint (Default: http://localhost:8000/ingest)
$env:AGENTSCOPE_INGEST_URL = "http://localhost:8000/ingest"

# AgentScope API Key (Required for authenticated ingestion)
$env:AGENTSCOPE_API_KEY = "your-secret-api-key"

# Client-Side Redaction Toggle (Default: false)
# Set to "true" to redact all input/output payloads client-side before sending
$env:AGENTSCOPE_REDACT_ENABLED = "false"
```

---

## 3. Choose Your Integration Path

### Path 1: LangGraph Integration (Zero-Rewrite Adapter)

For agents built with **LangGraph** or **LangChain**, attach `LangGraphAdapter` to your execution callbacks without altering agent business logic:

```python
from agentscope import LangGraphAdapter
from my_agent import graph

# 1. Instantiate the adapter
adapter = LangGraphAdapter(
    agent_id="customer-support-agent",
    trace_id="session-trace-001"
)

# 2. Pass adapter in execution callbacks
inputs = {"messages": [("user", "Hello, I need help with my order.")]}
result = graph.invoke(inputs, config={"callbacks": [adapter]})
```

---

### Path 2: Custom Agent / Decorator Path

For custom Python agent loops or frameworks outside LangGraph, use `@agentscope.trace` to mark agent boundaries/functions and `agentscope.patch()` to automatically instrument LLM clients. Delegation boundaries share execution context with patched calls, so trace IDs, parent spans, agent identity, delegation chains, and hop numbers do not need to be passed through business-function arguments:

```python
import agentscope
from agentscope import trace

# 1. Automatically instrument LLM calls (e.g. OpenAI and Anthropic).
# Fallback IDs apply only when a patched call runs outside a traced context.
agentscope.patch()

# 2. Decorate custom functions, tools, or agent nodes
@trace(name="web_search", span_type="tool_call")
def search_web(query: str) -> str:
    # Your custom search tool logic
    return f"Results for {query}"

@trace(name="specialist-agent", span_type="delegation")
async def specialist_agent(user_query: str):
    search_results = search_web(user_query)
    # A patched OpenAI/Anthropic call here automatically belongs to
    # specialist-agent and is parented beneath this span.
    return search_results

@trace(name="lead-agent", span_type="delegation")
async def run_research(user_query: str):
    return await specialist_agent(user_query)
```

For a root `delegation` span, `hop_number` is `0`; the first delegated agent is `1`, and so on. Supplying `agent_id=` remains supported, but when omitted a delegation span uses its `name` as the agent identity. Non-delegation spans inherit the active trace and parent context without extending the delegation chain.

When redaction is enabled, the SDK computes a process-local HMAC fingerprint of the pre-redaction input before replacing `input` and `output` with `[REDACTED]`. Only the truncated fingerprint is transmitted; the HMAC key and raw value remain local. This lets the existing Failure Loops rule distinguish repeated input from changing input even in redacted traces.

---

## 4. Verification

When your agent executes, telemetry spans are asynchronously sent to the AgentScope ingestion backend without blocking your host process or throwing exceptions into your agent code.

Quick checks against a running local stack:

```powershell
# Spans arriving? (through the Nginx front door)
curl http://localhost/traces

# Full span list for one trace, in arrival order
curl http://localhost/history/<trace_id-from-above>
```

The dashboard (Vite dev server) shows the live DAG and anomaly alerts at `http://localhost:5173`; in a deployment the dashboard is served behind the same Nginx front door as the API.

## 5. Guarantees (measured)

- **Fail-silent delivery:** if the backend is unreachable, the agent is unaffected — verified by killing the backend mid-run and observing the monitored agent complete 30/30 workloads with correct outputs and exit 0 (CHANGELOG 2026-08-22 00:45).
- **Client-side redaction:** with `AGENTSCOPE_REDACT_ENABLED=true`, raw `input`/`output` never leave your process — verified at the wire level (same changelog entry).
- **Overhead:** the latest three-process 100ms/node evaluation measured 4.81% mean overhead (95% t interval 1.28–8.33) and a 10.155ms mean absolute delta. The interval crosses 5%, so this is not an unconditional target-met claim; see `manuscript/evaluation-artifacts/2026-09-02-replicated/`.
