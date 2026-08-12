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
  trace_id: string;
  agent_id: string;
  details: any;
  is_anomaly: boolean;
};

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
        
        if (payload.is_anomaly) {
          setAnomalies((prev) => ({ ...prev, [payload.span_id]: payload as AnomalyEvent }));
          return;
        }

        // Otherwise assume it's a span:
        const span = payload as SpanEvent;
        setEvents((prev) => [...prev, span]);

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
