/**
 * AgentNode.tsx — Custom React Flow node for AgentScope.
 *
 * Card anatomy (UI redesign, FR-6):
 *   - Top row: type icon (shape encodes type) + small-caps type label,
 *     status chip top-right (shape encodes status: spinner/check/x/warning)
 *   - Bold operation name as the dominant element
 *   - Duration + token count as secondary metadata
 *
 * Visual states — distinguishable by icon SHAPE as well as color
 * (colorblind-safe, Week 9 a11y pass):
 *   - Running:   cyan pulsing border + spinning arc
 *   - Complete:  calm green border + check
 *   - Error:     red pulsing border + X
 *   - Anomalous: orange dashed border + glow + warning triangle —
 *     deliberately the loudest state; overrides the above.
 *
 * This component is identical for live and historical sources
 * (RULES.md §3 invariant #5).
 */

import { memo, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import AlertBadge from './AlertBadge';
import {
  IconLLM,
  IconTool,
  IconDelegation,
  IconState,
  IconFlow,
  IconSpinner,
  IconCheck,
  IconX,
  IconWarning,
  IconClock,
} from './icons';

/** Anomaly data shape, matching the worker's WS payload */
export interface AnomalyData {
  rule: string;
  description: string;
  timestamp: string;
}

export type SpanType = 'llm_call' | 'tool_call' | 'delegation' | 'state_update';
export type NodeStatus = 'active' | 'complete' | 'error';

/** The data shape stored in each custom node */
export interface AgentNodeData {
  label: string;
  spanType: SpanType;
  status: NodeStatus;
  agentId?: string;
  tokenUsage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number } | null;
  duration?: number | null;
  anomaly?: AnomalyData | null;
  onSelect?: (spanId: string) => void;
  [key: string]: unknown;
}

/** Type icons — SHAPE encodes type; tint stays neutral so color
 *  communicates status only (FR-6 a11y). */
const SPAN_TYPE_ICONS: Record<string, typeof IconLLM> = {
  llm_call: IconLLM,
  tool_call: IconTool,
  delegation: IconDelegation,
  state_update: IconState,
};

const SPAN_TYPE_LABELS: Record<string, string> = {
  llm_call: 'LLM Call',
  tool_call: 'Tool Call',
  delegation: 'Delegation',
  state_update: 'State Update',
};

/** Status icons — SHAPE encodes status (non-color cue, FR-6) */
const STATUS_ICONS: Record<string, typeof IconCheck> = {
  active: IconSpinner,
  complete: IconCheck,
  error: IconX,
};

/** CSS class suffix per node status */
const STATUS_CLASS: Record<string, string> = {
  active: 'agent-node--active',
  complete: 'agent-node--complete',
  error: 'agent-node--error',
};

function formatDuration(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

function AgentNode({ data, id }: NodeProps) {
  const nodeData = data as unknown as AgentNodeData;

  const TypeIcon = SPAN_TYPE_ICONS[nodeData.spanType] ?? IconFlow;
  const isAnomalous = Boolean(nodeData.anomaly);
  const StatusIcon = isAnomalous ? IconWarning : STATUS_ICONS[nodeData.status] ?? IconCheck;
  const statusKey = isAnomalous ? 'anomalous' : nodeData.status;

  let statusClass = STATUS_CLASS[nodeData.status] ?? '';
  if (isAnomalous) statusClass += ' agent-node--anomalous';

  const statusText = isAnomalous
    ? `anomalous (${nodeData.anomaly?.rule})`
    : nodeData.status;

  const onKeyDown = (e: ReactKeyboardEvent) => {
    // Keyboard access to the InspectPanel (Week 9 a11y pass, Flow 3 Step 4)
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      const onSelect = nodeData.onSelect as ((spanId: string) => void) | undefined;
      onSelect?.(id);
    }
  };

  return (
    <div
      className={`agent-node ${statusClass}`}
      id={`node-${nodeData.label}`}
      role="button"
      tabIndex={0}
      aria-label={`${SPAN_TYPE_LABELS[nodeData.spanType] ?? nodeData.spanType} node "${nodeData.label}", status ${statusText}. Press Enter to inspect.`}
      onKeyDown={onKeyDown}
    >
      {isAnomalous && <AlertBadge rule={nodeData.anomaly!.rule} />}

      <Handle type="target" position={Position.Top} className="agent-node__handle" />

      <div className="agent-node__top">
        <span className="agent-node__type-icon" aria-hidden="true">
          <TypeIcon size={13} />
        </span>
        <span className="agent-node__type">
          {SPAN_TYPE_LABELS[nodeData.spanType] ?? nodeData.spanType}
        </span>
        <span className={`agent-node__status-chip agent-node__status-chip--${statusKey}`} aria-hidden="true">
          <StatusIcon size={12} />
        </span>
      </div>

      <div className="agent-node__name" title={nodeData.label}>{nodeData.label}</div>

      <div className="agent-node__meta">
        <IconClock size={10} className="agent-node__meta-icon" aria-hidden="true" />
        <span>
          {nodeData.duration != null
            ? formatDuration(nodeData.duration)
            : nodeData.status === 'active'
              ? 'in progress'
              : '—'}
        </span>
        {nodeData.tokenUsage?.total_tokens != null && (
          <span className="agent-node__tokens">{nodeData.tokenUsage.total_tokens.toLocaleString()} tok</span>
        )}
      </div>

      <Handle type="source" position={Position.Bottom} className="agent-node__handle" />
    </div>
  );
}

export default memo(AgentNode);
