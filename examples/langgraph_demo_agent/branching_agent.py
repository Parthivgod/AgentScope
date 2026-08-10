import asyncio
from typing import Dict, Any, Literal
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from agentscope import LangGraphAdapter

class BranchingState(TypedDict):
    query: str
    route: str
    result: str

def router_node(state: BranchingState) -> Dict[str, Any]:
    query = state.get("query", "").lower()
    if "calc" in query or "math" in query:
        route = "calculator"
    elif "search" in query or "info" in query:
        route = "search"
    else:
        route = "general"
    return {"route": route}

def calculator_node(state: BranchingState) -> Dict[str, Any]:
    return {"result": f"[Calculator Node] Computed result for '{state['query']}'"}

def search_node(state: BranchingState) -> Dict[str, Any]:
    return {"result": f"[Search Node] Retrieved search results for '{state['query']}'"}

def general_node(state: BranchingState) -> Dict[str, Any]:
    return {"result": f"[General Node] Processed general query '{state['query']}'"}

def select_route(state: BranchingState) -> Literal["calculator", "search", "general"]:
    return state["route"]

def build_branching_graph():
    builder = StateGraph(BranchingState)
    builder.add_node("router", router_node)
    builder.add_node("calculator", calculator_node)
    builder.add_node("search", search_node)
    builder.add_node("general", general_node)
    
    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router",
        select_route,
        {
            "calculator": "calculator",
            "search": "search",
            "general": "general"
        }
    )
    builder.add_edge("calculator", END)
    builder.add_edge("search", END)
    builder.add_edge("general", END)
    
    return builder.compile()

async def run_branching_agent(query: str, agent_id: str = "branching-demo-agent", trace_id: str = "trace-branching-001"):
    graph = build_branching_graph()
    adapter = LangGraphAdapter(agent_id=agent_id, trace_id=trace_id)
    config = {"callbacks": [adapter]}
    
    initial_state = {"query": query, "route": "", "result": ""}
    result = await graph.ainvoke(initial_state, config=config)
    return result

if __name__ == "__main__":
    res_math = asyncio.run(run_branching_agent("Calculate 2 + 2"))
    print("Branching Agent Math Result:", res_math)
    res_search = asyncio.run(run_branching_agent("Search latest AI news"))
    print("Branching Agent Search Result:", res_search)
