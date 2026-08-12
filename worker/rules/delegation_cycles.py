from typing import Optional, Dict, Any, Set, Tuple
from agentscope.schema import Span

class DelegationCycleRule:
    name = "delegation_cycles"

    def __init__(self):
        # We need to track the path of delegations.
        # However, we only get spans as they are emitted (which is typically on_end or on_start).
        # We can maintain a trace_id -> active call stack (or visited set)
        # For simplicity, if agent A delegates to agent B, and agent B delegates to agent A,
        # we see span for A, and then span for B where B's parent is A's delegation span.
        # We will keep a map of trace_id -> span_id -> agent_id
        # And we can traverse parent_span_id to see if agent_id was already in the path.
        
        self.span_agent_map: Dict[str, Dict[str, str]] = {}
        # trace_id -> {span_id: (agent_id, parent_span_id)}
        self.trace_graphs: Dict[str, Dict[str, Tuple[str, Optional[str]]]] = {}

    def evaluate(self, span: Span) -> Optional[Dict[str, Any]]:
        trace_id = span.trace_id
        
        if trace_id not in self.trace_graphs:
            self.trace_graphs[trace_id] = {}
            
        self.trace_graphs[trace_id][span.span_id] = (span.agent_id, span.parent_span_id)
        
        # Traverse up the parent chain to see if the current agent_id appears
        current_parent = span.parent_span_id
        visited_agents = {span.agent_id}
        cycle_detected = False
        path = [span.agent_id]
        
        while current_parent:
            parent_info = self.trace_graphs[trace_id].get(current_parent)
            if not parent_info:
                break
                
            parent_agent_id, next_parent = parent_info
            path.append(parent_agent_id)
            
            if parent_agent_id == span.agent_id:
                # Cycle!
                cycle_detected = True
                break
                
            current_parent = next_parent

        if cycle_detected:
            # We found a cycle
            path.reverse()
            return {
                "reason": f"Delegation cycle detected. Agent '{span.agent_id}' was previously visited in this execution path.",
                "path": path
            }
            
        return None
