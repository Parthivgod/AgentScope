/**
 * InspectPanel.tsx — Slide-out detail panel for a selected span node.
 *
 * Shown when the user clicks a node in the execution graph (Flow 3, Step 4).
 * Displays: span name, type, agent ID, input/output, duration, token usage,
 * status + exception details.
 *
 * This component is designed to work identically for both live and
 * historical event sources (RULES.md §3 invariant #5).
 *
 * References:
 *   - Build Plan §4 Track C Week 4
 *   - Flow 3 Step 4: hover/click detail — input/output, duration, token usage
 *   - Flow 4 Step 4: click-to-inspect anomaly detail (future extension)
 */

import { type SpanEvent } from '../hooks/useWebSocket';
import './InspectPanel.css';

interface InspectPanelProps {
  span: SpanEvent | null;
  onClose: () => void;
}

/** Format an ISO date string to a clean HH:MM:SS.mmm display */
function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    fractionalSecondDigits: 3,
  } as Intl.DateTimeFormatOptions);
}

/** Compute duration in ms between two ISO timestamps */
function computeDuration(start: string, end: string | null): number | null {
  if (!end) return null;
  return new Date(end).getTime() - new Date(start).getTime();
}

/** Pretty-print JSON, truncating very long values */
function formatJSON(value: unknown): string {
  if (value == null) return '—';
  try {
    const str = JSON.stringify(value, null, 2);
    if (str.length > 2000) return str.slice(0, 2000) + '\n… (truncated)';
    return str;
  } catch {
    return String(value);
  }
}

const SPAN_TYPE_LABELS: Record<string, string> = {
  llm_call: 'LLM Call',
  tool_call: 'Tool Call',
  delegation: 'Delegation',
  state_update: 'State Update',
};

export default function InspectPanel({ span, onClose }: InspectPanelProps) {
  if (!span) return null;

  const duration = computeDuration(span.start_time, span.end_time);
  const isError = span.status.status === 'error';
  const isActive = span.end_time === null;

  return (
    <div className="inspect-panel" id="inspect-panel">
      {/* Backdrop */}
      <div className="inspect-panel__backdrop" onClick={onClose} />

      {/* Panel */}
      <div className="inspect-panel__content">
        {/* Header */}
        <div className="inspect-panel__header">
          <div className="inspect-panel__title-row">
            <h2 className="inspect-panel__title">{span.name}</h2>
            <button
              className="inspect-panel__close"
              onClick={onClose}
              aria-label="Close panel"
              id="inspect-panel-close"
            >
              ✕
            </button>
          </div>
          <div className="inspect-panel__subtitle">
            <span className={`inspect-panel__badge inspect-panel__badge--${span.span_type}`}>
              {SPAN_TYPE_LABELS[span.span_type] ?? span.span_type}
            </span>
            <span
              className={`inspect-panel__status ${
                isError
                  ? 'inspect-panel__status--error'
                  : isActive
                    ? 'inspect-panel__status--active'
                    : 'inspect-panel__status--success'
              }`}
            >
              {isError ? '● Error' : isActive ? '● Running' : '● Complete'}
            </span>
          </div>
        </div>

        {/* Body */}
        <div className="inspect-panel__body">
          {/* Timing section */}
          <section className="inspect-panel__section">
            <h3 className="inspect-panel__section-title">Timing</h3>
            <div className="inspect-panel__grid">
              <div className="inspect-panel__field">
                <span className="inspect-panel__field-label">Start</span>
                <span className="inspect-panel__field-value">{formatTime(span.start_time)}</span>
              </div>
              <div className="inspect-panel__field">
                <span className="inspect-panel__field-label">End</span>
                <span className="inspect-panel__field-value">
                  {span.end_time ? formatTime(span.end_time) : '—'}
                </span>
              </div>
              <div className="inspect-panel__field">
                <span className="inspect-panel__field-label">Duration</span>
                <span className="inspect-panel__field-value inspect-panel__field-value--mono">
                  {duration != null
                    ? duration >= 1000
                      ? `${(duration / 1000).toFixed(2)}s`
                      : `${duration}ms`
                    : isActive
                      ? 'In progress…'
                      : '—'}
                </span>
              </div>
            </div>
          </section>

          {/* Identity section */}
          <section className="inspect-panel__section">
            <h3 className="inspect-panel__section-title">Identity</h3>
            <div className="inspect-panel__grid">
              <div className="inspect-panel__field">
                <span className="inspect-panel__field-label">Agent ID</span>
                <span className="inspect-panel__field-value inspect-panel__field-value--mono">
                  {span.agent_id}
                </span>
              </div>
              <div className="inspect-panel__field">
                <span className="inspect-panel__field-label">Span ID</span>
                <span className="inspect-panel__field-value inspect-panel__field-value--mono">
                  {span.span_id}
                </span>
              </div>
              <div className="inspect-panel__field">
                <span className="inspect-panel__field-label">Trace ID</span>
                <span className="inspect-panel__field-value inspect-panel__field-value--mono">
                  {span.trace_id}
                </span>
              </div>
              {span.parent_span_id && (
                <div className="inspect-panel__field">
                  <span className="inspect-panel__field-label">Parent Span</span>
                  <span className="inspect-panel__field-value inspect-panel__field-value--mono">
                    {span.parent_span_id}
                  </span>
                </div>
              )}
            </div>
          </section>

          {/* Token Usage (only if populated) */}
          {span.token_usage &&
            (span.token_usage.prompt_tokens || span.token_usage.completion_tokens) && (
              <section className="inspect-panel__section">
                <h3 className="inspect-panel__section-title">Token Usage</h3>
                <div className="inspect-panel__token-bar">
                  <div className="inspect-panel__token-item">
                    <span className="inspect-panel__token-label">Prompt</span>
                    <span className="inspect-panel__token-value">
                      {span.token_usage.prompt_tokens ?? 0}
                    </span>
                  </div>
                  <div className="inspect-panel__token-item">
                    <span className="inspect-panel__token-label">Completion</span>
                    <span className="inspect-panel__token-value">
                      {span.token_usage.completion_tokens ?? 0}
                    </span>
                  </div>
                  <div className="inspect-panel__token-item inspect-panel__token-item--total">
                    <span className="inspect-panel__token-label">Total</span>
                    <span className="inspect-panel__token-value">
                      {span.token_usage.total_tokens ?? 0}
                    </span>
                  </div>
                </div>
              </section>
            )}

          {/* Error details */}
          {isError && span.status.exception_details && (
            <section className="inspect-panel__section">
              <h3 className="inspect-panel__section-title inspect-panel__section-title--error">
                Exception
              </h3>
              <pre className="inspect-panel__code inspect-panel__code--error">
                {span.status.exception_details}
              </pre>
            </section>
          )}

          {/* Input */}
          <section className="inspect-panel__section">
            <h3 className="inspect-panel__section-title">Input</h3>
            <pre className="inspect-panel__code">{formatJSON(span.input)}</pre>
          </section>

          {/* Output */}
          <section className="inspect-panel__section">
            <h3 className="inspect-panel__section-title">Output</h3>
            <pre className="inspect-panel__code">{formatJSON(span.output)}</pre>
          </section>
        </div>
      </div>
    </div>
  );
}
