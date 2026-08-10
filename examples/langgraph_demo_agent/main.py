import asyncio
import logging
from linear_agent import run_linear_agent
from branching_agent import run_branching_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("langgraph_demo_agent")

async def main():
    logger.info("--- Starting AgentScope LangGraph Demo Agent ---")
    
    logger.info("Running Linear Graph Flow...")
    linear_result = await run_linear_agent(
        agent_id="langgraph-linear-agent",
        trace_id="trace-linear-demo-1"
    )
    logger.info(f"Linear Graph Output: {linear_result['output_text']}")
    
    logger.info("Running Branching Graph Flow (Calculator Route)...")
    calc_result = await run_branching_agent(
        query="Calculate 42 * 10",
        agent_id="langgraph-branching-agent",
        trace_id="trace-branching-demo-1"
    )
    logger.info(f"Branching Graph Output (Math): {calc_result['result']}")

    logger.info("Running Branching Graph Flow (Search Route)...")
    search_result = await run_branching_agent(
        query="Search system status",
        agent_id="langgraph-branching-agent",
        trace_id="trace-branching-demo-2"
    )
    logger.info(f"Branching Graph Output (Search): {search_result['result']}")
    
    # Allow background event sender task to flush queue
    await asyncio.sleep(1)
    logger.info("--- LangGraph Demo Agent Execution Complete ---")

if __name__ == "__main__":
    asyncio.run(main())
