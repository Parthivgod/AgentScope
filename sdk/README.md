# AgentScope SDK

Zero-rewrite observability instrumentation for multi-agent LLM systems.

- **Flow 1 — LangGraph adapter:** attach `LangGraphAdapter` via `config["callbacks"]`; no changes to agent business logic.
- **Flow 2 — decorator + patching:** `@agentscope.trace` for custom functions/tools; `agentscope.patch()` for OpenAI and Anthropic clients.

Both paths emit schema-identical spans and deliver them asynchronously, fail-silent — the monitored agent is never blocked or crashed by telemetry.

## Install

```bash
pip install -e ./sdk            # base (decorator + patch paths)
pip install -e ./sdk[langgraph] # + LangGraph adapter path
```

See `docs/sdk-quickstart.md` in the repository root for a five-minute guide, environment variables (`AGENTSCOPE_INGEST_URL`, `AGENTSCOPE_API_KEY`, `AGENTSCOPE_REDACT_ENABLED`), and verification steps.
