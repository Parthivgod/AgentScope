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
  _agentscope_stream?: string;
  _agentscope_stream_id?: string;
  _agentscope_event_cursor?: string;
  _agentscope_anomaly_cursor?: string;
};

export type AnomalyEvent = {
  rule: string;
  span_id: string;
  trace_id: string;
  agent_id: string;
  details: any;
  is_anomaly: boolean;
  _agentscope_stream?: string;
  _agentscope_stream_id?: string;
  _agentscope_event_cursor?: string;
  _agentscope_anomaly_cursor?: string;
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
            // FR-8 / Flow 5: /history now returns the worker-persisted anomaly
            // flags alongside spans. Map them into the SAME shape the live WS
            // path produces, so downstream node-state computation (invariant #5)
            // is shared, not duplicated per mode.
            const flags: Record<string, AnomalyEvent> = {};
            for (const a of data.anomalies || []) {
              if (a?.span_id) flags[a.span_id] = a as AnomalyEvent;
            }
            setAnomalies(flags);
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

    // Live mode — with automatic reconnection (demo-readiness: a dropped WS
    // must not silently freeze the dashboard; reconnect with backoff instead).
    let ws: WebSocket | null = null;
    let closedByCleanup = false;
    let retry = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let lastEventId: string | null = null;
    let lastAnomalyId: string | null = null;

    const connect = () => {
      const resumeUrl = new URL(url, window.location.href);
      if (lastEventId) resumeUrl.searchParams.set('last_event_id', lastEventId);
      if (lastAnomalyId) resumeUrl.searchParams.set('last_anomaly_id', lastAnomalyId);
      ws = new WebSocket(resumeUrl.toString());

      ws.onopen = () => {
        retry = 0;
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);

          if (payload._agentscope_event_cursor) {
            lastEventId = payload._agentscope_event_cursor;
          }
          if (payload._agentscope_anomaly_cursor) {
            lastAnomalyId = payload._agentscope_anomaly_cursor;
          }
          if (payload._agentscope_stream_id && !payload._agentscope_event_cursor && !payload._agentscope_anomaly_cursor) {
            if (payload._agentscope_stream === 'agentscope:anomalies') {
              lastAnomalyId = payload._agentscope_stream_id;
            } else if (payload._agentscope_stream === 'agentscope:events') {
              lastEventId = payload._agentscope_stream_id;
            }
          }

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
        if (!closedByCleanup) {
          const delay = Math.min(1000 * 2 ** retry, 10000);
          retry += 1;
          reconnectTimer = setTimeout(connect, delay);
        }
      };

      ws.onerror = () => {
        // onclose follows onerror; reconnection is handled there
        setIsConnected(false);
      };
    };

    connect();

    return () => {
      closedByCleanup = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [url, mode, traceId]);

  return { events, anomalies, isConnected, error };
}
