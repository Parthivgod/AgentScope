/**
 * AnomalyPanel.tsx — Plain-language anomaly detail with per-rule evidence,
 * rendered inside the InspectPanel when the selected span was flagged.
 *
 * Evidence is derived client-side from the flag `details` plus the span
 * events the dashboard already holds (anomalyEvidence.ts) — the same data
 * in live and historical modes, so rendering is identical (invariant #5).
 *
 * The strongest element (per the design reference): the CALL PATTERN
 * timeline for Failure Loops — the repeated calls with token counts and
 * outcomes, legible at a glance. Built generically: each of the six rules
 * gets the evidence view its data actually supports.
 *
 * References:
 *   - FR-8, Flow 4 Step 4: anomaly alerting + click-to-inspect detail
 *   - RULES.md §3 #7: detection, not enforcement — this panel only
 *     explains; it never offers actions on the monitored agent.
 */

import { useMemo, type CSSProperties } from 'react';
import { type AnomalyEvent, type SpanEvent } from '../hooks/useEventSource';
import { buildAnomalyEvidence, ruleLabel, RULE_META, type PatternStep } from '../anomalyEvidence';
import { IconWarning, IconArrowRight, IconCheck, IconX, IconSpinner } from './icons';
import './AnomalyPanel.css';

interface AnomalyPanelProps {
  anomaly: AnomalyEvent;
  events: SpanEvent[];
}

function formatDuration(ms: number | null): string {
  if (ms == null) return '…';
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

function OutcomeGlyph({ outcome }: { outcome: PatternStep['outcome'] }) {
  if (outcome === 'error') return <IconX size={12} className="anomaly-panel__outcome-icon anomaly-panel__outcome-icon--error" />;
  if (outcome === 'running') return <IconSpinner size={12} className="anomaly-panel__outcome-icon anomaly-panel__outcome-icon--running" />;
  return <IconCheck size={12} className="anomaly-panel__outcome-icon anomaly-panel__outcome-icon--success" />;
}

function CallPattern({ steps, repeatCount, windowSeconds }: { steps: PatternStep[]; repeatCount: number; windowSeconds: number }) {
  if (steps.length === 0) {
    return <p className="anomaly-panel__note">The repeated calls are not in the current event window.</p>;
  }
  const overflow = repeatCount - steps.length;
  return (
    <div>
      <div className="anomaly-panel__pattern" role="list" aria-label="Call pattern, oldest first">
        {steps.map((step, i) => (
          <div role="listitem" key={i} className={`anomaly-panel__step anomaly-panel__step--${step.outcome}`}>
            <span className="anomaly-panel__step-index">{i + 1}</span>
            <span className="anomaly-panel__step-name" title={step.name}>{step.name}</span>
            <span className="anomaly-panel__step-meta">
              {step.tokens != null ? `${step.tokens.toLocaleString()} tok · ` : ''}
              {formatDuration(step.durationMs)}
            </span>
            <OutcomeGlyph outcome={step.outcome} />
          </div>
        ))}
      </div>
      <p className="anomaly-panel__pattern-footer">
        Identical call repeated{' '}
        <strong>{repeatCount}×</strong> within {windowSeconds}s
        {overflow > 0 ? ` (showing first ${steps.length})` : ''}
      </p>
    </div>
  );
}

function ThresholdBar({ value, threshold, unit, metricLabel }: { value: number; threshold: number; unit: string; metricLabel: string }) {
  const scaleMaximum = Math.max(value, threshold * 1.15, 1);
  const valuePct = (value / scaleMaximum) * 100;
  const thresholdPct = (threshold / scaleMaximum) * 100;
  const over = value > threshold;
  const barStyle = {
    '--evidence-value': `${valuePct}%`,
    '--evidence-threshold': `${thresholdPct}%`,
  } as CSSProperties;
  return (
    <div>
      <div className="anomaly-panel__bar-labels">
        <span className="anomaly-panel__bar-metric">{metricLabel}</span>
        <span className={`anomaly-panel__bar-value ${over ? 'anomaly-panel__bar-value--over' : ''}`}>
          {value.toLocaleString()}{unit} / {threshold.toLocaleString()}{unit}
        </span>
      </div>
      <div
        className="anomaly-panel__bar"
        role="img"
        aria-label={`${metricLabel}: ${value}${unit} against threshold ${threshold}${unit}`}
        style={barStyle}
      >
        <div className={`anomaly-panel__bar-fill ${over ? 'anomaly-panel__bar-fill--over' : ''}`} />
        <div className="anomaly-panel__bar-threshold" aria-hidden="true" />
      </div>
      {over && <p className="anomaly-panel__note">Exceeds the threshold by {(value - threshold).toLocaleString()}{unit}.</p>}
    </div>
  );
}

function PathEvidence({ path, repeatedAgent }: { path: string[]; repeatedAgent: string }) {
  if (path.length === 0) return null;
  return (
    <div className="anomaly-panel__path" aria-label="Delegation path">
      {path.map((agent, i) => {
        const isRepeat = agent === repeatedAgent && i > path.indexOf(agent);
        return (
          <span key={i} className="anomaly-panel__path-group" >
            {i > 0 && <IconArrowRight size={12} className="anomaly-panel__path-arrow" />}
            <span className={`anomaly-panel__path-chip ${isRepeat ? 'anomaly-panel__path-chip--repeat' : ''}`}>
              {agent}
              {isRepeat && <span className="anomaly-panel__path-repeat">↻ repeat</span>}
            </span>
          </span>
        );
      })}
    </div>
  );
}

export default function AnomalyPanel({ anomaly, events }: AnomalyPanelProps) {
  const evidence = useMemo(() => buildAnomalyEvidence(anomaly, events), [anomaly, events]);
  const meta = RULE_META[anomaly.rule];
  const reason =
    typeof anomaly.details?.reason === 'string' && anomaly.details.reason
      ? anomaly.details.reason
      : null;
  const description = meta?.description ?? reason ?? 'This span matched an anomaly detection rule.';

  return (
    <section className="anomaly-panel" aria-label="Anomaly detail">
      <div className="anomaly-panel__header">
        <span className="anomaly-panel__header-icon"><IconWarning size={16} /></span>
        <div>
          <h3 className="anomaly-panel__title">Anomaly Detected</h3>
          <span className="anomaly-panel__rule-chip">{ruleLabel(anomaly.rule)}</span>
        </div>
      </div>

      <p className="anomaly-panel__description">{description}</p>
      {reason && reason !== description && (
        <p className="anomaly-panel__reason"><strong>Observed:</strong> {reason}</p>
      )}

      <div className="anomaly-panel__evidence">
        {evidence.kind === 'call-pattern' && (
          <>
            <h4 className="anomaly-panel__evidence-title">Call pattern</h4>
            <CallPattern steps={evidence.steps} repeatCount={evidence.repeatCount} windowSeconds={evidence.windowSeconds} />
          </>
        )}
        {evidence.kind === 'threshold' && (
          <ThresholdBar value={evidence.value} threshold={evidence.threshold} unit={evidence.unit} metricLabel={evidence.metricLabel} />
        )}
        {evidence.kind === 'exception' && (
          <>
            {evidence.exceptionDetails && (
              <pre className="anomaly-panel__exception">{evidence.exceptionDetails}</pre>
            )}
            {evidence.outputEmpty && (
              <p className="anomaly-panel__note">The LLM call completed but its output was empty.</p>
            )}
            {!evidence.exceptionDetails && !evidence.outputEmpty && (
              <p className="anomaly-panel__note">The step reported an error status.</p>
            )}
          </>
        )}
        {evidence.kind === 'path' && <PathEvidence path={evidence.path} repeatedAgent={evidence.repeatedAgent} />}
        {evidence.kind === 'unknown' && (
          <pre className="anomaly-panel__exception">{JSON.stringify(evidence.details, null, 2)}</pre>
        )}
      </div>
    </section>
  );
}
