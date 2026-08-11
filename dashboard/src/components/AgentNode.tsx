/**
 * AgentNode.tsx — Custom React Flow node for AgentScope.
 *
 * Renders a single span node with three visual states:
 *   - Active (pulsing border glow) — span in-flight, end_time === null
 *   - Complete (solid success) — span finished without error
 *   - Error (red glow) — span ended with status 'error'
 *
 * References:
 *   - Flow 3 Steps 2-3: pulsing active node, real-time appearance
 *   - Flow 4 Step 3: anomalous node has distinct visual state (future)
 *   - FR-6: visually distinguishing active/idle/anomalous nodes
 */

import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import AlertBadge from './AlertBadge';

/**
 * Anomaly definition (Mocked for Week 6, matching expected structure)
 */
export interface AnomalyData {
  rule: string;
  description: string;
  timestamp: string;
}

/** The data shape stored in each custom node */
export interface AgentNodeData {
  label: string;
  spanType: 'llm_call' | 'tool_call' | 'delegation' | 'state_update';
  status: 'active' | 'complete' | 'error';
  agentId?: string;
  tokenUsage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number } | null;
  duration?: number | null;
  anomaly?: AnomalyData | null;
  [key: string]: unknown;
}

/** Icons (emoji) per span type — lightweight, no icon library needed */
const SPAN_TYPE_ICONS: Record<string, string> = {
  llm_call: '🤖',
  tool_call: '🔧',
  delegation: '📡',
  state_update: '📝',
};

/** CSS class suffix per node status */
const STATUS_CLASS: Record<string, string> = {
  active: 'agent-node--active',
  complete: 'agent-node--complete',
  error: 'agent-node--error',
};

function AgentNode({ data }: NodeProps) {
  const nodeData = data as unknown as AgentNodeData;
  const icon = SPAN_TYPE_ICONS[nodeData.spanType] ?? '⚙️';
  let statusClass = STATUS_CLASS[nodeData.status] ?? '';
  
  if (nodeData.anomaly) {
    statusClass += ' agent-node--anomalous';
  }

  return (
    <div className={`agent-node ${statusClass}`} id={`node-${nodeData.label}`}>
      {nodeData.anomaly && <AlertBadge rule={nodeData.anomaly.rule} />}
      
      <Handle type="target" position={Position.Top} className="agent-node__handle" />

      <div className="agent-node__header">
        <span className="agent-node__icon">{icon}</span>
        <span className="agent-node__type">{nodeData.spanType.replace('_', ' ')}</span>
        {nodeData.status === 'active' && !nodeData.anomaly && (
          <span className="agent-node__live-dot" />
        )}
      </div>

      <div className="agent-node__label">{nodeData.label}</div>

      {nodeData.duration != null && (
        <div className="agent-node__meta">
          {nodeData.duration >= 1000
            ? `${(nodeData.duration / 1000).toFixed(1)}s`
            : `${nodeData.duration}ms`}
          {nodeData.tokenUsage?.total_tokens != null && (
            <span className="agent-node__tokens">
              · {nodeData.tokenUsage.total_tokens} tok
            </span>
          )}
        </div>
      )}

      <Handle type="source" position={Position.Bottom} className="agent-node__handle" />
    </div>
  );
}

export default memo(AgentNode);

