# Support-Triage Multi-Agent Demo (real LLM calls)

A genuinely multi-agent support-triage system — supervisor/router, three
specialists, and a response composer — instrumented via AgentScope's
zero-rewrite LangGraphAdapter path (Flow 1). **The LLM calls are real**
(classification, specialist reasoning, and response drafting all hit the
OpenAI API); only the tools are local synthetic fixtures, with deterministic
"poison" conditions that trigger four different anomaly rules for a reliable
demo. This is honest engineering: the LLM does real work; the failure
conditions are the same category of thing that causes real anomalies in
production (a flaky downstream tool, a hung diagnostic, a bloated context) —
not rigged LLM responses.

This example is **additive** — it does not modify the existing
`langgraph_demo_agent` or `custom_demo_agent` examples.

## Requirements

- **AWS credentials must be set** (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`) — this demo makes real, billable LLM calls against **GPT-OSS 120B on Amazon Bedrock** (model `openai.gpt-oss-120b-1:0`), evaluated and selected for these roles on 2026-08-22 (plain text-in/text-out is all the demo needs; the specialists' tools are invoked by graph code, not model-driven tool calling, which sidesteps the unreliable LangChain-on-Bedrock tool-calling paths).
- AgentScope local stack running (`infra/docker compose up -d`).
- `pip install langchain-aws boto3` (in addition to `requirements.txt`).
- `AGENTSCOPE_API_KEY=test-key` (local stack default).
- `pip install -r requirements.txt && pip install -e ../../sdk`

## Model tier & cost guardrails (demo-app design, not AgentScope's)

- **Model: GPT-OSS 120B on Bedrock** (`openai.gpt-oss-120b-1:0`, override with `TRIAGE_MODEL`), via `ChatBedrockConverse`. Open-weight model on pay-per-token Bedrock pricing; output tokens are capped at 1024 per call so reasoning stays brief (long reasoning both slows demo pacing and can push spans toward the 30s timeout ceiling). A full 8-ticket run costs on the order of a few cents.
- **Hard per-run ceiling of 15 LLM calls** (`agent.py`, `CallBudget`) — if a
  bug ever causes a runaway loop, the demo aborts instead of burning budget.
  This is the demo application's own responsible design; AgentScope itself
  still only observes (RULES.md detection-not-enforcement boundary).

## Tickets

| Ticket | Behavior | Rule it triggers |
|---|---|---|
| `HAPPY-*` (4 tickets) | Normal routing and resolution | **none** (false-positive check) |
| `DELEGATION-CYCLE-001` | Billing and Technical each correctly disown the ticket; routing bounces back to a previously visited agent | `delegation_cycles` |
| `FAIL-LOOP-002` | Account store returns an ambiguous record; agent retries the identical lookup 5× | `failure_loops` (≥4 identical/60s) |
| `TIMEOUT-003` | Diagnostic tool hangs 31s for this ticket only | `timeouts` (>30s) |
| `TOKEN-SPIKE-004` | Ticket carries ~100KB of history into the composer's single LLM call | `token_spikes` (>8k tokens/call) |

Note: `TIMEOUT-003` takes ~35s to run by design.

## Running

```powershell
$env:AWS_ACCESS_KEY_ID = "..."
$env:AWS_SECRET_ACCESS_KEY = "..."
$env:AWS_REGION = "us-east-1"
$env:AGENTSCOPE_API_KEY = "test-key"
$env:AGENTSCOPE_INGEST_URL = "http://localhost:8000/ingest"

python main.py happy    # false-positive check first
python main.py poison   # the four triggers
python main.py all
```

Dashboard (`dashboard/`, `npm run dev`, http://localhost:5173) in Live mode
shows the router → specialist → composer hierarchy with real edges. See
`RUN_ORDER.md` for the scripted demo sequence.

## The zero-rewrite point

`agent.py` contains the entire multi-agent system and imports nothing from
AgentScope. Observability is attached in `main.py` alone:

```python
adapter = LangGraphAdapter(agent_id="support-triage", trace_id=...,
                           agent_id_by_run=AGENT_ID_BY_RUN)
graph.ainvoke(state, config={"callbacks": [adapter]})
```

`agent_id_by_run` gives each agent in the graph its own span identity, which
is what makes delegation-cycle detection meaningful in a multi-agent graph.

## Tests

`test_support_demo.py` — offline (no API key): tool poison conditions, token
spike sizing (tiktoken-verified >8k), adapter id mapping, call ceiling.
