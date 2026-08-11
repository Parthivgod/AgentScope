/**
 * useWebSocket.ts — WebSocket hook for consuming live span events.
 *
 * Week 2-3 status: Uses a mock data generator that simulates a
 * realistic multi-agent LangGraph execution flow. The mock produces
 * schema-identical events to what Track B's real WebSocket relay
 * will deliver once ws.py is available.
 *
 * BLOCKED: Real WebSocket integration is blocked on Track B's ws.py
 * deliverable (Build Plan §4 Track B Week 3). Once available, the
 * hook internals swap from mock → real WS; the consumer interface
 * (events + isConnected) stays identical.
 *
 * References:
 *   - Build Plan §4 Track C Week 2: mock WS built against schema
 *   - Build Plan §4 Track C Week 3: connect to Track B's real WS relay
 *   - PRD §6.3: event/span schema
 */

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

/**
 * Expected shape of an anomaly event from Track B the Anomaly Worker (Week 6)
 */
export type AnomalyEvent = {
  rule: string;
  span_id: string;
  description: string;
  timestamp: string;
};

/**
 * Generate a realistic mock span sequence simulating a branching
 * LangGraph agent: Router → search_web (tool), gpt-4o (LLM),
 * then a delegation to a sub-agent with its own tool call.
 */
function createMockSpanSequence(): SpanEvent[] {
  const now = Date.now();

  return [
    // 1. Root delegation starts
    {
      trace_id: 't-demo-1', span_id: 'router', parent_span_id: null,
      span_type: 'delegation', name: 'Router Agent',
      input: { query: 'Find recent papers on agent observability' },
      output: null,
      start_time: new Date(now).toISOString(), end_time: null,
      status: { status: 'success' }, token_usage: null, agent_id: 'router',
    },

    // 2. Tool call starts
    {
      trace_id: 't-demo-1', span_id: 'search-1', parent_span_id: 'router',
      span_type: 'tool_call', name: 'search_web',
      input: { query: 'agent observability 2026', max_results: 5 },
      output: null,
      start_time: new Date(now + 800).toISOString(), end_time: null,
      status: { status: 'success' }, token_usage: null, agent_id: 'router',
    },

    // 3. Tool call completes
    {
      trace_id: 't-demo-1', span_id: 'search-1', parent_span_id: 'router',
      span_type: 'tool_call', name: 'search_web',
      input: { query: 'agent observability 2026', max_results: 5 },
      output: { results: ['AgentSight (2025)', 'GAAT (2026)', 'AgentTrace (2026)'] },
      start_time: new Date(now + 800).toISOString(),
      end_time: new Date(now + 2200).toISOString(),
      status: { status: 'success' }, token_usage: null, agent_id: 'router',
    },

    // 4. LLM reasoning call starts
    {
      trace_id: 't-demo-1', span_id: 'llm-1', parent_span_id: 'router',
      span_type: 'llm_call', name: 'gpt-4o',
      input: { messages: [{ role: 'user', content: 'Summarize search results' }] },
      output: null,
      start_time: new Date(now + 2500).toISOString(), end_time: null,
      status: { status: 'success' },
      token_usage: { prompt_tokens: 340, completion_tokens: 0, total_tokens: 340 },
      agent_id: 'router',
    },

    // 5. LLM call completes with token usage
    {
      trace_id: 't-demo-1', span_id: 'llm-1', parent_span_id: 'router',
      span_type: 'llm_call', name: 'gpt-4o',
      input: { messages: [{ role: 'user', content: 'Summarize search results' }] },
      output: { response: 'Found 3 relevant papers on agent observability...' },
      start_time: new Date(now + 2500).toISOString(),
      end_time: new Date(now + 4100).toISOString(),
      status: { status: 'success' },
      token_usage: { prompt_tokens: 340, completion_tokens: 180, total_tokens: 520 },
      agent_id: 'router',
    },

    // 6. Delegation to sub-agent starts
    {
      trace_id: 't-demo-1', span_id: 'writer', parent_span_id: 'router',
      span_type: 'delegation', name: 'Writer Agent',
      input: { task: 'Draft summary paragraph' },
      output: null,
      start_time: new Date(now + 4400).toISOString(), end_time: null,
      status: { status: 'success' }, token_usage: null, agent_id: 'writer',
    },

    // 7. Sub-agent LLM call starts
    {
      trace_id: 't-demo-1', span_id: 'llm-2', parent_span_id: 'writer',
      span_type: 'llm_call', name: 'gpt-4o',
      input: { messages: [{ role: 'system', content: 'You are a technical writer.' }] },
      output: null,
      start_time: new Date(now + 4800).toISOString(), end_time: null,
      status: { status: 'success' },
      token_usage: { prompt_tokens: 420, completion_tokens: 0, total_tokens: 420 },
      agent_id: 'writer',
    },

    // 8. Sub-agent LLM call errors (rate limit)
    {
      trace_id: 't-demo-1', span_id: 'llm-2', parent_span_id: 'writer',
      span_type: 'llm_call', name: 'gpt-4o',
      input: { messages: [{ role: 'system', content: 'You are a technical writer.' }] },
      output: null,
      start_time: new Date(now + 4800).toISOString(),
      end_time: new Date(now + 6500).toISOString(),
      status: { status: 'error', exception_details: 'RateLimitError: Rate limit exceeded. Retry after 12s.' },
      token_usage: { prompt_tokens: 420, completion_tokens: 0, total_tokens: 420 },
      agent_id: 'writer',
    },

    // 9. Writer agent completes with error
    {
      trace_id: 't-demo-1', span_id: 'writer', parent_span_id: 'router',
      span_type: 'delegation', name: 'Writer Agent',
      input: { task: 'Draft summary paragraph' },
      output: null,
      start_time: new Date(now + 4400).toISOString(),
      end_time: new Date(now + 6800).toISOString(),
      status: { status: 'error', exception_details: 'Sub-agent failed: RateLimitError' },
      token_usage: null, agent_id: 'writer',
    },

    // 10. Root agent completes with error
    {
      trace_id: 't-demo-1', span_id: 'router', parent_span_id: null,
      span_type: 'delegation', name: 'Router Agent',
      input: { query: 'Find recent papers on agent observability' },
      output: null,
      start_time: new Date(now).toISOString(),
      end_time: new Date(now + 7200).toISOString(),
      status: { status: 'error', exception_details: 'Downstream agent Writer Agent failed' },
      token_usage: null, agent_id: 'router',
    },
  ];
}

export function useWebSocket(url: string) {
  const [events, setEvents] = useState<SpanEvent[]>([]);
  const [anomalies, setAnomalies] = useState<Record<string, AnomalyEvent>>({});
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    const ws = new WebSocket(url);

    ws.onopen = () => {
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        
        // Track B Week 6 gap: Real anomaly events logic will parse distinct payloads.
        // For now, if the payload looks like an anomaly, parse it:
        if (payload.rule && payload.span_id) {
          setAnomalies((prev) => ({ ...prev, [payload.span_id]: payload as AnomalyEvent }));
          return;
        }

        // Otherwise assume it's a span:
        const span = payload as SpanEvent;
        setEvents((prev) => [...prev, span]);

        // MOCK ANOMALY GENERATOR:
        // Automatically mock an anomaly for demo purposes if it's a tool_call
        // This is a temporary substitute for the missing Track B integration.
        if (span.span_type === 'tool_call' && !span.end_time) {
          setTimeout(() => {
            setAnomalies((prev) => {
              if (prev[span.span_id]) return prev; // already flagged
              return {
                ...prev,
                [span.span_id]: {
                  rule: 'Failure Loops',
                  span_id: span.span_id,
                  description: 'Call repeated ≥4 times within 60s without state progression.',
                  timestamp: new Date().toISOString(),
                }
              };
            });
          }, 4000);
        }

      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
    };

    ws.onerror = (err) => {
      console.error('WebSocket error:', err);
      setIsConnected(false);
    };

    return () => {
      ws.close();
    };
  }, [url]);

  return { events, anomalies, isConnected };
}
