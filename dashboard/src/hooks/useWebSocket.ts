import { useEffect, useState } from 'react';

export type SpanStatus = {
  status: 'success' | 'error';
  exception_details?: string;
};

export type TokenUsage = {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
};

export type SpanEvent = {
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  span_type: 'llm_call' | 'tool_call' | 'delegation' | 'state_update';
  name: string;
  input: any;
  output: any;
  start_time: string;
  end_time: string | null;
  status: SpanStatus;
  token_usage: TokenUsage | null;
  agent_id: string;
};

// Mock data generator for Week 2
export function useWebSocket(url: string) {
  const [events, setEvents] = useState<SpanEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    // Week 2: Mock WebSocket implementation (Flow 3)
    setIsConnected(true);

    const mockSpans: SpanEvent[] = [
      {
        trace_id: "t1", span_id: "s1", parent_span_id: null, span_type: "delegation", 
        name: "Agent 1", input: null, output: null, start_time: new Date().toISOString(), end_time: null, 
        status: { status: 'success' }, token_usage: null, agent_id: "agent-1"
      },
      {
        trace_id: "t1", span_id: "s2", parent_span_id: "s1", span_type: "tool_call", 
        name: "search_web", input: { query: 'test' }, output: null, start_time: new Date(Date.now() + 1000).toISOString(), end_time: null, 
        status: { status: 'success' }, token_usage: null, agent_id: "agent-1"
      },
      {
        trace_id: "t1", span_id: "s2", parent_span_id: "s1", span_type: "tool_call", 
        name: "search_web", input: { query: 'test' }, output: "results", start_time: new Date(Date.now() + 1000).toISOString(), end_time: new Date(Date.now() + 2000).toISOString(), 
        status: { status: 'success' }, token_usage: null, agent_id: "agent-1"
      },
      {
        trace_id: "t1", span_id: "s3", parent_span_id: "s1", span_type: "llm_call", 
        name: "gpt-4", input: { prompt: 'query' }, output: null, start_time: new Date(Date.now() + 2500).toISOString(), end_time: null, 
        status: { status: 'success' }, token_usage: null, agent_id: "agent-1"
      },
      {
        trace_id: "t1", span_id: "s3", parent_span_id: "s1", span_type: "llm_call", 
        name: "gpt-4", input: { prompt: 'query' }, output: null, start_time: new Date(Date.now() + 2500).toISOString(), end_time: new Date(Date.now() + 3000).toISOString(), 
        status: { status: 'error', exception_details: 'Rate limit exceeded' }, token_usage: null, agent_id: "agent-1"
      },
      {
        trace_id: "t1", span_id: "s1", parent_span_id: null, span_type: "delegation", 
        name: "Agent 1", input: null, output: "done", start_time: new Date().toISOString(), end_time: new Date(Date.now() + 3500).toISOString(), 
        status: { status: 'error', exception_details: 'Failed to complete due to LLM error' }, token_usage: null, agent_id: "agent-1"
      }
    ];

    let index = 0;
    const interval = setInterval(() => {
      if (index < mockSpans.length) {
        const newEvent = mockSpans[index];
        setEvents((prev) => [...prev, newEvent]);
        index++;
      } else {
        clearInterval(interval);
      }
    }, 1500);

    return () => {
      clearInterval(interval);
      setIsConnected(false);
    };
  }, [url]);

  return { events, isConnected };
}
