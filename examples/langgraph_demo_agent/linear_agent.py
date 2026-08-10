import asyncio
from typing import Dict, Any
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from agentscope import LangGraphAdapter

class AgentState(TypedDict):
    input_text: str
    processed_data: str
    output_text: str

def fetch_data(state: AgentState) -> Dict[str, Any]:
    return {"processed_data": f"Fetched data for '{state['input_text']}'"}

def analyze_data(state: AgentState) -> Dict[str, Any]:
    return {"processed_data": f"{state['processed_data']} -> Analyzed"}

def format_response(state: AgentState) -> Dict[str, Any]:
    return {"output_text": f"Final Response: {state['processed_data']}"}

def build_linear_graph():
    builder = StateGraph(AgentState)
    builder.add_node("fetch_data", fetch_data)
    builder.add_node("analyze_data", analyze_data)
    builder.add_node("format_response", format_response)
    
    builder.add_edge(START, "fetch_data")
    builder.add_edge("fetch_data", "analyze_data")
    builder.add_edge("analyze_data", "format_response")
    builder.add_edge("format_response", END)
    
    return builder.compile()

async def run_linear_agent(agent_id: str = "linear-demo-agent", trace_id: str = "trace-linear-001"):
    graph = build_linear_graph()
    adapter = LangGraphAdapter(agent_id=agent_id, trace_id=trace_id)
    config = {"callbacks": [adapter]}
    
    initial_state = {"input_text": "Sample query for linear agent", "processed_data": "", "output_text": ""}
    result = await graph.ainvoke(initial_state, config=config)
    return result

if __name__ == "__main__":
    res = asyncio.run(run_linear_agent())
    print("Linear Agent Result:", res)
