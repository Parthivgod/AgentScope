/**
 * App.tsx — Root component for the AgentScope dashboard.
 *
 * Responsibilities:
 *   1. Consumes span events from the WebSocket hook
 *   2. Builds and maintains the React Flow node/edge graph
 *   3. Applies dagre layout on every graph change (layout.ts)
 *   4. Renders custom AgentNode components with visual states
 *   5. Opens InspectPanel on node click (Flow 3, Step 4)
 *
 * This component is the single rendering path for both live and
 * historical event sources (RULES.md §3 invariant #5). The only
 * difference between modes is the event source passed to the hook.
 *
 * References:
 *   - FR-6:  live hierarchical graph, active/idle/anomalous states
 *   - Flow 3: first live monitoring session
 *   - Flow 5: historical replay (same component, different source — future)
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeMouseHandler,
  BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { useEventSource, type SpanEvent } from './hooks/useEventSource';
import { getLayoutedElements } from './layout';
import AgentNode, { type AgentNodeData } from './components/AgentNode';
import InspectPanel from './components/InspectPanel';

import './components/AgentNode.css';
import './App.css';

/** Registry of custom node types for React Flow */
const nodeTypes = { agentNode: AgentNode };

/** Derive visual status from a span event */
function spanStatus(event: SpanEvent): 'active' | 'complete' | 'error' {
  if (event.status.status === 'error') return 'error';
  if (event.end_time === null) return 'active';
  return 'complete';
}

/** Compute duration in ms between two ISO timestamps */
function computeDuration(start: string, end: string | null): number | null {
  if (!end) return null;
  return new Date(end).getTime() - new Date(start).getTime();
}

export default function App() {
  const [mode, setMode] = useState<'live' | 'historical'>('live');
  const [historicalTraceId, setHistoricalTraceId] = useState<string | null>(null);
  const [traceIds, setTraceIds] = useState<string[]>([]);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const { events, anomalies, isConnected, error } = useEventSource('ws://localhost:5173/ws', mode, historicalTraceId);

  // ── Reset the graph when switching modes or selecting another trace ─
  useEffect(() => {
    setNodes([]);
    setEdges([]);
    setSpanMap(new Map());
    setSelectedSpanId(null);
  }, [mode, mode === 'historical' ? historicalTraceId : null, setNodes, setEdges]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Load available trace IDs when entering historical mode ────────
  useEffect(() => {
    if (mode !== 'historical') return;

    const controller = new AbortController();
    fetch('/traces', { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`Trace list request failed (HTTP ${res.status}).`);
        return res.json();
      })
      .then((data) => {
        const ids: string[] = data.trace_ids || [];
        setTraceIds(ids);
        setHistoricalTraceId((current) =>
          current && ids.includes(current) ? current : ids[0] ?? null
        );
      })
      .catch((err) => {
        if (err.name !== 'AbortError') console.error('Error fetching trace list:', err);
      });

    return () => controller.abort();
  }, [mode]);

  // Track the raw span data keyed by span_id for InspectPanel lookups
  const [spanMap, setSpanMap] = useState<Map<string, SpanEvent>>(new Map());

  // Currently selected span for inspection
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const selectedSpan = selectedSpanId ? spanMap.get(selectedSpanId) ?? null : null;
  const selectedAnomaly = selectedSpanId ? anomalies[selectedSpanId] ?? null : null;

  // ── Process incoming events → build nodes/edges ───────────────────
  useEffect(() => {
    if (events.length === 0) return;

    // Build a map of the latest state for each span_id
    const latestSpans = new Map<string, SpanEvent>();
    for (const e of events) {
      latestSpans.set(e.span_id, e);
    }

    setSpanMap(latestSpans);

    setNodes((currentNodes) => {
      const nextNodes = [];
      const currentNodesMap = new Map(currentNodes.map((n) => [n.id, n]));

      for (const [spanId, latestEvent] of latestSpans.entries()) {
        const existingNode = currentNodesMap.get(spanId);
        
        const anomalyEvent = anomalies[spanId];
        let anomalyData = null;
        if (anomalyEvent) {
          anomalyData = {
            rule: anomalyEvent.rule,
            description: anomalyEvent.details?.message || 'Anomaly detected',
            timestamp: new Date().toISOString(),
          };
        }

        const nodeData: AgentNodeData = {
          label: latestEvent.name,
          spanType: latestEvent.span_type,
          status: spanStatus(latestEvent),
          agentId: latestEvent.agent_id,
          tokenUsage: latestEvent.token_usage,
          duration: computeDuration(latestEvent.start_time, latestEvent.end_time),
          anomaly: anomalyData,
        };

        if (existingNode) {
          nextNodes.push({ ...existingNode, data: nodeData });
        } else {
          nextNodes.push({
            id: spanId,
            type: 'agentNode',
            position: { x: 0, y: 0 },
            data: nodeData,
          });
        }
      }
      return nextNodes;
    });

    setEdges((currentEdges) => {
      const nextEdges = [];
      const currentEdgesMap = new Map(currentEdges.map((e) => [e.id, e]));

      for (const latestEvent of latestSpans.values()) {
        if (latestEvent.parent_span_id) {
          const edgeId = `e-${latestEvent.parent_span_id}-${latestEvent.span_id}`;
          const existingEdge = currentEdgesMap.get(edgeId);

          if (existingEdge) {
            nextEdges.push({
              ...existingEdge,
              animated: latestEvent.end_time === null,
            });
          } else {
            nextEdges.push({
              id: edgeId,
              source: latestEvent.parent_span_id,
              target: latestEvent.span_id,
              animated: latestEvent.end_time === null,
              style: { stroke: '#475569', strokeWidth: 1.5 },
            });
          }
        }
      }
      return nextEdges;
    });
  }, [events, anomalies, setNodes, setEdges]);

  // ── Apply dagre layout whenever nodes/edges change ────────────────
  useEffect(() => {
    if (nodes.length === 0) return;

    const { nodes: layoutedNodes } = getLayoutedElements(nodes, edges, {
      direction: 'TB',
      nodesep: 60,
      ranksep: 100,
    });

    // Only update if positions actually changed (avoid infinite loop)
    const positionsChanged = layoutedNodes.some((ln, i) => {
      const orig = nodes[i];
      return (
        orig &&
        (Math.abs(ln.position.x - orig.position.x) > 0.5 ||
          Math.abs(ln.position.y - orig.position.y) > 0.5)
      );
    });

    if (positionsChanged) {
      setNodes(layoutedNodes);
    }
  }, [nodes.length, edges.length]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Node click handler → open InspectPanel ────────────────────────
  const onNodeClick: NodeMouseHandler = useCallback((_event, node) => {
    setSelectedSpanId(node.id);
  }, []);

  const onPanelClose = useCallback(() => {
    setSelectedSpanId(null);
  }, []);

  // ── Count stats for the header bar ────────────────────────────────
  const stats = useMemo(() => {
    let active = 0;
    let errors = 0;
    let anomaliesCount = 0;
    nodes.forEach((n) => {
      const data = n.data as AgentNodeData;
      if (data.status === 'active') active++;
      if (data.status === 'error') errors++;
      if (data.anomaly) anomaliesCount++;
    });
    return { total: nodes.length, active, errors, anomalies: anomaliesCount };
  }, [nodes]);

  const isRedacted = useMemo(() => {
    return events.some(e => 
      (e.input && JSON.stringify(e.input).includes('[REDACTED]')) ||
      (e.output && JSON.stringify(e.output).includes('[REDACTED]'))
    );
  }, [events]);

  return (
    <div className="app" id="agentscope-dashboard">
      {/* ── Header bar ─────────────────────────────────────────── */}
      <header className="app__header" id="dashboard-header">
        <div className="app__header-left">
          <h1 className="app__logo">
            <span className="app__logo-icon">◉</span> AgentScope
          </h1>
          <span className={`app__connection ${isConnected ? 'app__connection--on' : ''}`}>
            {isConnected ? 'Live' : mode === 'historical' ? 'Historical' : 'Disconnected'}
          </span>
          {isRedacted && (
            <span className="app__badge app__badge--redacted" style={{ background: '#ef4444', color: 'white', padding: '2px 8px', borderRadius: '12px', fontSize: '0.75rem', fontWeight: 600, marginLeft: '8px' }}>
              🔒 Redacted Data
            </span>
          )}

          <div className="app__mode-toggles" style={{ marginLeft: '1.5rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <button 
              className={`app__toggle-btn ${mode === 'live' ? 'app__toggle-btn--active' : ''}`}
              onClick={() => setMode('live')}
              style={{ background: mode === 'live' ? '#3b82f6' : '#1e293b', color: '#fff', border: 'none', padding: '4px 12px', borderRadius: '4px', cursor: 'pointer', fontSize: '0.875rem' }}
            >
              Live
            </button>
            <button 
              className={`app__toggle-btn ${mode === 'historical' ? 'app__toggle-btn--active' : ''}`}
              onClick={() => setMode('historical')}
              style={{ background: mode === 'historical' ? '#3b82f6' : '#1e293b', color: '#fff', border: 'none', padding: '4px 12px', borderRadius: '4px', cursor: 'pointer', fontSize: '0.875rem' }}
            >
              Historical Replay
            </button>
            {mode === 'historical' && (
              <select
                value={historicalTraceId || ''}
                onChange={(e) => setHistoricalTraceId(e.target.value)}
                style={{ background: '#0f172a', color: '#cbd5e1', border: '1px solid #334155', padding: '4px 8px', borderRadius: '4px', fontSize: '0.875rem', marginLeft: '0.5rem', cursor: 'pointer' }}
              >
                {traceIds.length === 0 && <option value="">No traces recorded</option>}
                {traceIds.map((id) => (
                  <option key={id} value={id}>Trace: {id}</option>
                ))}
              </select>
            )}
          </div>
        </div>
        <div className="app__header-right">
          <div className="app__stat">
            <span className="app__stat-value">{stats.total}</span>
            <span className="app__stat-label">Nodes</span>
          </div>
          <div className="app__stat">
            <span className="app__stat-value app__stat-value--active">{stats.active}</span>
            <span className="app__stat-label">Active</span>
          </div>
          {stats.errors > 0 && (
            <div className="app__stat">
              <span className="app__stat-value app__stat-value--error">{stats.errors}</span>
              <span className="app__stat-label">Errors</span>
            </div>
          )}
          {stats.anomalies > 0 && (
            <div className="app__stat">
              <span className="app__stat-value app__stat-value--anomalous" style={{ color: '#fbbf24' }}>{stats.anomalies}</span>
              <span className="app__stat-label">Anomalies</span>
            </div>
          )}
          <div className="app__stat">
            <span className="app__stat-value">{events.length}</span>
            <span className="app__stat-label">Events</span>
          </div>
        </div>
      </header>

      {/* ── Historical-load error banner ─────────────────────────── */}
      {mode === 'historical' && error && (
        <div role="alert" style={{ background: '#7f1d1d', color: '#fecaca', padding: '8px 16px', fontSize: '0.875rem' }}>
          Historical replay unavailable: {error}
        </div>
      )}

      {/* ── Graph canvas ───────────────────────────────────────── */}
      <div className="app__canvas" id="graph-canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          proOptions={{ hideAttribution: true }}
        >
          <Controls
            className="app__controls"
            showInteractive={false}
          />
          <MiniMap
            className="app__minimap"
            nodeColor={(node) => {
              const data = node.data as AgentNodeData;
              if (data.status === 'error') return '#f87171';
              if (data.status === 'active') return '#22d3ee';
              return '#4ade80';
            }}
            maskColor="rgba(0, 0, 0, 0.7)"
          />
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1}
            color="rgba(255, 255, 255, 0.04)"
          />
        </ReactFlow>
      </div>

      {/* ── Inspect panel (shown on node click) ────────────────── */}
      <InspectPanel span={selectedSpan} anomaly={selectedAnomaly} onClose={onPanelClose} />
    </div>
  );
}

