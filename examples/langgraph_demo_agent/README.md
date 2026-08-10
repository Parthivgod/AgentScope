# LangGraph Demo Agent — AgentScope Instrumentation Example

This directory contains example LangGraph agents instrumented with AgentScope's `LangGraphAdapter` (Build Plan §4 Track A Week 4, Flow 1).

## Included Agents

1. **Linear Graph (`linear_agent.py`)**
   - A sequential 3-node execution pipeline (`fetch_data` -> `analyze_data` -> `format_response`).
   - Illustrates zero-rewrite instrumentation on standard linear workflows.

2. **Branching Graph (`branching_agent.py`)**
   - A conditional graph with a router node delegating dynamically to `calculator`, `search`, or `general` nodes based on input queries.
   - Demonstrates span capture across conditional edges and dynamic routing.

## Usage

Set environment variables (optional, defaults to `http://localhost:8000/ingest`):
```bash
export AGENTSCOPE_API_KEY="your-api-key"
export AGENTSCOPE_INGEST_URL="http://localhost:8000/ingest"
```

Run the demo suite:
```bash
python main.py
```
