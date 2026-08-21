# AgentScope Demo Script (local stack)

Talking points for a live demo against the LOCAL docker-compose deployment. The recorded video is a team task — this script is what to say and run. No AWS-dependent claims: everything below runs locally.

## Pre-demo checklist (5 min before)

1. `cd infra && AGENTSCOPE_API_KEY=test-key docker compose up -d` — all four services healthy.
2. Reset clean seed data: `docker compose exec redis redis-cli FLUSHDB`, then run the demo agent once (step 3 below) so `/traces` shows the three demo traces.
3. Dashboard running: `cd dashboard && npm run dev` → open `http://localhost:5173`.
4. Run `node scripts/demo-readiness-test.mjs` once — expect `DEMO-READY: PASS` (it checks console errors, replay, live anomaly rendering).

## The demo (≈5 minutes)

**1. Zero-rewrite instrumentation (~1 min).**
Show `examples/langgraph_demo_agent/main.py` and `branching_agent.py` — the only observability code is two lines: instantiate `LangGraphAdapter`, pass it in `config["callbacks"]`. No business-logic changes.

**2. Live execution graph (~1.5 min).**
With the dashboard in Live mode, run:
```bash
cd examples/langgraph_demo_agent
AGENTSCOPE_API_KEY=test-key AGENTSCOPE_INGEST_URL=http://localhost/ingest python main.py
```
Talking points: nodes appear as spans start (⟳ pulsing), edges show parent/child delegation, dagre lays out the hierarchy top-to-bottom; click a node to open the InspectPanel (inputs, outputs, tokens, timing — everything keyboard-accessible).

**3. Anomaly alert, live (~1.5 min).**
Run the failure injection from `docs/usability-test-prep.md` (8 failing tool_calls, ~12s).
Talking points: the agent's flaky tool fires the crashes rule — the node flips to the anomalous state (amber, dashed border, ⚠ badge, pulsing glow) *while the run is happening*, not after; the InspectPanel shows the rule and exception details. Emphasize: AgentScope only surfaces the problem — it never touches the monitored agent.

**4. Historical replay (~1 min).**
Switch the dashboard to Historical Replay; the dropdown lists the real traces just recorded; select `trace-linear-demo-1` — identical rendering to live, because it is the same rendering path with a different event source.

**5. Security close (~30s).**
```bash
curl -i -X POST http://localhost/ingest -H 'Content-Type: application/json' -d '{}'   # 401
curl -sk https://localhost:8443/traces                                                # TLS-terminated
```
No valid key, no ingestion; TLS terminates at Nginx.

## Optional (if asked)

- Redaction: re-run the demo agent with `AGENTSCOPE_REDACT_ENABLED=true` — the 🔒 badge appears and payloads are scrubbed before leaving the process.
- Resilience: `docker compose stop backend` mid-run — the agent completes normally; observability never risks availability.
