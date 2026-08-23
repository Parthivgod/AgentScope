/**
 * anomalyEvidence.ts — Derive human-readable evidence view-models from an
 * anomaly flag + the span events the dashboard already holds.
 *
 * This is pure client-side derivation: no new backend fields, no new
 * endpoints. Both live and historical modes hold the SAME `SpanEvent[]`
 * (invariant #5), so evidence renders identically in both modes by
 * construction.
 *
 * References:
 *   - FR-8 / Flow 4 Step 4: click-to-inspect anomaly detail
 *   - worker/rules/*: the six detectors and their `details` payloads
 */

import type { AnomalyEvent, SpanEvent } from './hooks/useEventSource';

/* ── Rule metadata: display name + plain-language description ─────── */

export const RULE_META: Record<string, { label: string; description: string }> = {
  failure_loops: {
    label: 'Failure Loop',
    description:
      'Repeated identical calls with the same inputs — the agent appears stuck in a retry loop instead of making progress.',
  },
  crashes: {
    label: 'Crash',
    description: 'This step failed with an error, or an LLM call completed without producing any output.',
  },
  timeouts: {
    label: 'Timeout',
    description: 'This step ran far longer than the configured timeout ceiling.',
  },
  token_spikes: {
    label: 'Token Spike',
    description: 'Token usage exceeded the configured safety threshold.',
  },
  message_storms: {
    label: 'Message Storm',
    description: 'An unusually high rate of events was emitted in a short window.',
  },
  delegation_cycles: {
    label: 'Delegation Cycle',
    description: 'Work was delegated back to an agent that already appeared in this execution path — a cycle.',
  },
};

export function ruleLabel(rule: string): string {
  return RULE_META[rule]?.label ?? rule.replace(/_/g, ' ');
}

/* ── Evidence view-model types ────────────────────────────────────── */

export interface PatternStep {
  name: string;
  tokens: number | null;
  durationMs: number | null;
  outcome: 'success' | 'error' | 'running';
}

export type Evidence =
  /** failure_loops — reconstructed sequence of identical calls */
  | { kind: 'call-pattern'; steps: PatternStep[]; repeatCount: number; windowSeconds: number }
  /** timeouts / token_spikes / message_storms — a value vs its threshold */
  | { kind: 'threshold'; value: number; threshold: number; unit: string; metricLabel: string }
  /** crashes — exception text / empty-output note */
  | { kind: 'exception'; exceptionDetails: string | null; outputEmpty: boolean }
  /** delegation_cycles — the agent path with the repeat */
  | { kind: 'path'; path: string[]; repeatedAgent: string }
  /** unknown rule — raw details fallback */
  | { kind: 'unknown'; details: Record<string, unknown> };

/* ── Helpers ──────────────────────────────────────────────────────── */

/** Stable JSON key ordering — matches how the worker's signature groups
 *  calls (name + sorted-input equality, worker/rules/failure_loops.py). */
function stableStringify(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value) ?? 'null';
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  const keys = Object.keys(value as Record<string, unknown>).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify((value as Record<string, unknown>)[k])}`).join(',')}}`;
}

/** Latest span state per span_id, ordered by start_time. */
function latestSpansByStart(events: SpanEvent[]): SpanEvent[] {
  const latest = new Map<string, SpanEvent>();
  for (const e of events) latest.set(e.span_id, e);
  return [...latest.values()].sort(
    (a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime()
  );
}

/** Extract the numeric threshold a rule's `reason` string mentions,
 *  e.g. "…exceeded timeout ceiling (30s)" → 30, "…threshold (8000)" → 8000. */
function thresholdFromReason(reason: string | undefined, fallback: number): number {
  if (!reason) return fallback;
  // Match the threshold label specifically. Token-spike reasons contain the
  // observed value first (for example, "usage (12000) ... threshold (8000)"),
  // so taking the first parenthesized number would make value and threshold
  // incorrectly appear equal in the evidence bar.
  const m =
    reason.match(/threshold(?:\s+ceiling)?\s*\(([\d.]+)\s*s?\)/i) ??
    reason.match(/threshold\s+([\d.]+)/i);
  const parsed = m ? Number(m[1]) : NaN;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function asRecord(details: unknown): Record<string, unknown> {
  return details && typeof details === 'object' ? (details as Record<string, unknown>) : {};
}

function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/* ── Main derivation ──────────────────────────────────────────────── */

export function buildAnomalyEvidence(anomaly: AnomalyEvent, events: SpanEvent[]): Evidence {
  const details = asRecord(anomaly.details);
  const reason = typeof details.reason === 'string' ? details.reason : undefined;

  switch (anomaly.rule) {
    case 'failure_loops': {
      // Reconstruct the repeated-call sequence: every span from the same
      // agent with the same name + same input as the flagged span, in
      // start-time order. (The flag itself only carries a hash + count —
      // the sequence lives in the events we already render.)
      const flagged = events.find((e) => e.span_id === anomaly.span_id);
      const steps: PatternStep[] = [];
      if (flagged) {
        const inputSig = stableStringify(flagged.input);
        for (const e of latestSpansByStart(events)) {
          if (e.agent_id !== flagged.agent_id || e.name !== flagged.name) continue;
          if (stableStringify(e.input) !== inputSig) continue;
          const durationMs =
            e.end_time != null
              ? new Date(e.end_time).getTime() - new Date(e.start_time).getTime()
              : null;
          steps.push({
            name: e.name,
            tokens: e.token_usage?.total_tokens ?? null,
            durationMs,
            outcome:
              e.status.status === 'error' ? 'error' : e.end_time == null ? 'running' : 'success',
          });
        }
      }
      // The count the worker actually observed (may exceed rendered steps).
      const fromReason = reason?.match(/seen (\d+) times/i);
      const repeatCount = fromReason ? Number(fromReason[1]) : steps.length;
      const windowFromReason = reason?.match(/within (\d+)s/i);
      return {
        kind: 'call-pattern',
        steps: steps.slice(0, 8),
        repeatCount: Math.max(repeatCount, steps.length),
        windowSeconds: windowFromReason ? Number(windowFromReason[1]) : 60,
      };
    }

    case 'timeouts': {
      const duration = num(details.duration_seconds);
      const threshold = thresholdFromReason(reason, 30);
      return {
        kind: 'threshold',
        value: duration ?? threshold,
        threshold,
        unit: 's',
        metricLabel: 'Duration vs timeout ceiling',
      };
    }

    case 'token_spikes': {
      const single = num(details.tokens);
      if (single != null) {
        return {
          kind: 'threshold',
          value: single,
          threshold: thresholdFromReason(reason, 8000),
          unit: ' tok',
          metricLabel: 'Single-call tokens vs threshold',
        };
      }
      return {
        kind: 'threshold',
        value: num(details.cumulative_tokens) ?? 0,
        threshold: thresholdFromReason(reason, 20000),
        unit: ' tok',
        metricLabel: 'Tokens in last 60s vs threshold',
      };
    }

    case 'message_storms': {
      const count = num(details.event_count);
      return {
        kind: 'threshold',
        value: count ?? 0,
        threshold: thresholdFromReason(reason, 20),
        unit: ' events',
        metricLabel: 'Events in window vs threshold',
      };
    }

    case 'crashes': {
      const exceptionDetails =
        typeof details.exception_details === 'string' ? details.exception_details : null;
      const outputEmpty = reason?.includes('empty output') ?? false;
      return { kind: 'exception', exceptionDetails, outputEmpty };
    }

    case 'delegation_cycles': {
      const rawPath = Array.isArray(details.path) ? details.path : [];
      const path = rawPath.filter((p): p is string => typeof p === 'string');
      // The cycle closes at the first agent that repeats.
      const seen = new Set<string>();
      let repeatedAgent = '';
      for (const agent of path) {
        if (seen.has(agent)) {
          repeatedAgent = agent;
          break;
        }
        seen.add(agent);
      }
      return { kind: 'path', path, repeatedAgent };
    }

    default:
      return { kind: 'unknown', details };
  }
}
