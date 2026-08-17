/**
 * useEventSource.ts — Hook for consuming span events, supporting live WS and historical mode.
 *
 * References:
 *   - Build Plan §4 Track C Week 7: historical replay
 *   - RULES.md invariant #5: one rendering component fed by multiple event sources
 */

import { useEffect, useState } from 'react';
import { mockHistoryPayload, mockHistoricalAnomalies } from './mockHistory';

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

export type AnomalyEvent = {
  rule: string;
  span_id: string;
  trace_id: string;
  agent_id: string;
  details: any;
  is_anomaly: boolean;
};

export function useEventSource(url: string, mode: 'live' | 'historical', traceId: string | null) {
  const [events, setEvents] = useState<SpanEvent[]>([]);
  const [anomalies, setAnomalies] = useState<Record<string, AnomalyEvent>>({});
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    // Clear state when mode or trace ID changes
    setEvents([]);
    setAnomalies({});

    if (mode === 'historical') {
      setIsConnected(false); // Not a live connection
      
      // Temporary mock for Track B's missing history.py endpoint
      if (traceId) {
        // Simulate a network fetch delay
        const timer = setTimeout(() => {
          setEvents(mockHistoryPayload);
          const anoms: Record<string, AnomalyEvent> = {};
          for (const a of mockHistoricalAnomalies) {
            anoms[a.span_id] = a;
          }
          setAnomalies(anoms);
        }, 300);
        return () => clearTimeout(timer);
      }
      return;
    }

    // Live mode
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
  }, [url, mode, traceId]);

  return { events, anomalies, isConnected };
}
