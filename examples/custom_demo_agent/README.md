# AgentScope — Custom Demo Agent

This example demonstrates **User Flow 2 (Custom Agent Path)** for non-LangGraph Python agent workflows using AgentScope's manual instrumentation capabilities:

1. `@agentscope.trace`: Decorator to instrument custom Python functions, tool calls, and reasoning steps.
2. `agentscope.patch(openai)`: Auto-patches OpenAI client calls to record LLM spans.

## Prerequisites

- Python 3.9+
- AgentScope SDK (`pip install -e ../../sdk`)
- Running AgentScope Ingestion Service (`http://localhost:8000/ingest`)

## Running the Demo

```bash
# 1. Set environment variables
export AGENTSCOPE_API_KEY="your-api-key"
export AGENTSCOPE_INGEST_URL="http://localhost:8000/ingest"

# 2. Run main script
python main.py
```

## Running Tests

```bash
python -m pytest test_demo_e2e.py
```
