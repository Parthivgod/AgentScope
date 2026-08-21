/**
 * useEventSource.ts — Hook for consuming span events, supporting live WS and historical mode.
 *
 * References:
 *   - Build Plan §4 Track C Week 7: historical replay
 *   - RULES.md invariant #5: one rendering component fed by multiple event sources
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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Clear state when mode or trace ID changes
    setEvents([]);
    setAnomalies({});
    setError(null);

    if (mode === 'historical') {
      setIsConnected(false); // Not a live connection

      if (traceId) {
        const controller = new AbortController();
        fetch(`/history/${traceId}`, {
          signal: controller.signal
        })
          .then(res => {
            if (res.status === 404) throw new Error(`Trace "${traceId}" not found — no spans recorded for it.`);
            if (!res.ok) throw new Error(`History request failed (HTTP ${res.status}).`);
            return res.json();
          })
          .then(data => {
            setEvents(data.spans || []);
            // Anomalies aren't returned by history.py yet
            setAnomalies({});
          })
          .catch(err => {
            if (err.name !== 'AbortError') {
              console.error('Error fetching historical trace:', err);
              setError(err.message || 'Failed to load historical trace.');
            }
          });

        return () => controller.abort();
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

  return { events, anomalies, isConnected, error };
}
