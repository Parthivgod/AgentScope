import { type SpanEvent, type AnomalyEvent } from './useEventSource';

export const mockHistoryPayload: SpanEvent[] = [
  {
    trace_id: 't-history-001',
    span_id: 'span-h-1',
    parent_span_id: null,
    span_type: 'llm_call',
    name: 'Historical Root Span',
    input: { prompt: 'Who won the 2022 World Cup?' },
    output: null,
    start_time: '2026-08-17T12:00:00Z',
    end_time: null,
    status: { status: 'success' },
    token_usage: null,
    agent_id: 'qa_agent',
  },
  {
    trace_id: 't-history-001',
    span_id: 'span-h-2',
    parent_span_id: 'span-h-1',
    span_type: 'tool_call',
    name: 'Search Web',
    input: { query: '2022 World Cup winner' },
    output: { result: '[REDACTED]' },
    start_time: '2026-08-17T12:00:01Z',
    end_time: '2026-08-17T12:00:02Z',
    status: { status: 'success' },
    token_usage: null,
    agent_id: 'search_plugin',
  },
  {
    trace_id: 't-history-001',
    span_id: 'span-h-1',
    parent_span_id: null,
    span_type: 'llm_call',
    name: 'Historical Root Span',
    input: { prompt: 'Who won the 2022 World Cup?' },
    output: { text: 'Argentina won the 2022 World Cup.' },
    start_time: '2026-08-17T12:00:00Z',
    end_time: '2026-08-17T12:00:05Z',
    status: { status: 'success' },
    token_usage: { prompt_tokens: 50, completion_tokens: 15, total_tokens: 65 },
    agent_id: 'qa_agent',
  }
];

export const mockHistoricalAnomalies: AnomalyEvent[] = [
  {
    rule: 'Slow Tool Call',
    span_id: 'span-h-2',
    trace_id: 't-history-001',
    agent_id: 'search_plugin',
    details: { message: 'Search took longer than expected.' },
    is_anomaly: true,
  }
];
