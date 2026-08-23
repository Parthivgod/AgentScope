import asyncio
import os
import sys

# Ensure SDK is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sdk")))

from custom_agent import run_custom_agent
from agentscope.sender import sender

async def main():
    print("==================================================")
    print("AgentScope Demo: Custom Agent Manual Instrumentation")
    print("==================================================")
    print("Demonstrating User Flow 2 (Custom / Non-LangGraph Agent)")
    print("Using @agentscope.trace and patch(openai) for span capture...\n")

    query = "How does AgentScope instrument non-LangGraph custom agents?"
    print(f"User Query: {query}\n")

    result = await run_custom_agent(query=query, agent_id="custom-demo-agent", trace_id="demo-custom-trace-001")

    # This short-lived demo performs an explicit bounded shutdown flush so
    # its final completion events are visible before the process exits.
    try:
        await asyncio.wait_for(sender.queue.join(), timeout=10)
    except asyncio.TimeoutError:
        pass
    
    print("\nExecution Completed Successfully!")
    print(f"Final Summary: {result['summary']}")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(main())
