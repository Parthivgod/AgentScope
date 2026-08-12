import asyncio
import os
import sys
import logging
from typing import Dict, Any

# Ensure SDK is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sdk")))

import agentscope
from agentscope import trace, patch

logger = logging.getLogger(__name__)

# Manual instrumentation for custom functions/tools using @agentscope.trace
@trace(name="fetch_web_data", span_type="tool_call", agent_id="custom-demo-agent")
async def fetch_web_data(query: str) -> Dict[str, Any]:
    """Simulates fetching web data as a custom tool call."""
    await asyncio.sleep(0.05)
    return {
        "query": query,
        "results": [
            {"title": "AgentScope Overview", "snippet": "Self-hosted LLM observability framework."},
            {"title": "Manual Instrumentation Guide", "snippet": "Use @agentscope.trace and patch() for non-LangGraph agents."}
        ]
    }

@trace(name="process_search_results", span_type="tool_call", agent_id="custom-demo-agent")
async def process_search_results(data: Dict[str, Any]) -> str:
    """Processes and formats raw search results into a text prompt."""
    await asyncio.sleep(0.02)
    results = data.get("results", [])
    snippets = [f"- {item['title']}: {item['snippet']}" for item in results]
    return "Retrieved context:\n" + "\n".join(snippets)

@trace(name="generate_summary", span_type="llm_call", agent_id="custom-demo-agent")
async def generate_summary(context: str, query: str) -> str:
    """Simulates generating a response summary."""
    await asyncio.sleep(0.05)
    return f"Summary for '{query}': AgentScope enables visibility across custom agents via manual instrumentation."

async def run_custom_agent(query: str = "Explain AgentScope instrumentation", agent_id: str = "custom-demo-agent", trace_id: str = "custom-trace-001") -> Dict[str, Any]:
    """
    Executes the custom agent workflow.
    Demonstrates Flow 2 (Custom Agent Path) using @agentscope.trace and patch(openai).
    """
    # Apply OpenAI auto-patching if requested/available
    patch(agent_id=agent_id, trace_id=trace_id)

    # 1. Execute tool call 1
    raw_data = await fetch_web_data(query)

    # 2. Execute tool call 2
    context = await process_search_results(raw_data)

    # 3. Execute LLM summary generation
    summary = await generate_summary(context, query)

    return {
        "query": query,
        "context": context,
        "summary": summary,
        "status": "success"
    }

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Running Custom Demo Agent...")
    res = asyncio.run(run_custom_agent())
    print(f"Result: {res}")
