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
 * Shell (UI redesign, FR-6 / Flow 3 / Flow 4): header with run context,
 * prominent anomaly-count badge, segmented LIVE/HISTORICAL toggle,
 * connection-status and redaction indicators (read-only — redaction is
 * decided client-side in the SDK, Decision #4), and an at-a-glance
 * stats bar. Every element renders identically in both modes.
 *
 * References:
 *   - FR-6:  live hierarchical graph, active/idle/anomalous states
 *   - Flow 3: first live monitoring session
 *   - Flow 4: anomaly alerting at a glance
 *   - Flow 5: historical replay (same component, different source)
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
import Legend from './components/Legend';
import {
  IconGraph,
  IconCheckCircle,
  IconActivity,
  IconXCircle,
  IconWarning,
  IconLock,
  IconEye,
} from './components/icons';

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
            // Every rule emits details.reason (worker/rules/*) — the old
            // `details?.message` read never matched, so descriptions always
            // fell back to the generic string. Fixed in the UI redesign.
            description: anomalyEvent.details?.reason || 'Anomaly detected',
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
          // Keyboard path into the InspectPanel (Week 9 a11y pass)
          onSelect: (spanId: string) => setSelectedSpanId(spanId),
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

  // ── Count stats for the stats bar ─────────────────────────────────
  const stats = useMemo(() => {
    let active = 0;
    let complete = 0;
    let errors = 0;
    let anomaliesCount = 0;
    nodes.forEach((n) => {
      const data = n.data as AgentNodeData;
      if (data.status === 'active') active++;
      if (data.status === 'complete') complete++;
      if (data.status === 'error') errors++;
      if (data.anomaly) anomaliesCount++;
    });
    return { total: nodes.length, complete, active, errors, anomalies: anomaliesCount };
  }, [nodes]);

  // ── Run context for the header (trace + agents) ───────────────────
  const runContext = useMemo(() => {
    const traceId = mode === 'historical' ? historicalTraceId : events[0]?.trace_id ?? null;
    const agents = [...new Set(events.map((e) => e.agent_id))];
    return { traceId, agents };
  }, [events, mode, historicalTraceId]);

  const agentsLabel =
    runContext.agents.length === 0
      ? null
      : runContext.agents.length <= 3
        ? runContext.agents.join(' · ')
        : `${runContext.agents.length} agents`;

  // ── Redaction state — READ-ONLY indicator (Decision #4): redaction
  //    is decided client-side in the SDK; the dashboard only reports
  //    what it received (inferred from [REDACTED] markers). ──────────
  const isRedacted = useMemo(() => {
    return events.some((e) =>
      (e.input && JSON.stringify(e.input).includes('[REDACTED]')) ||
      (e.output && JSON.stringify(e.output).includes('[REDACTED]'))
    );
  }, [events]);

  const connection = mode === 'historical'
    ? { label: 'Replay', state: 'replay' as const }
    : isConnected
      ? { label: 'Connected', state: 'on' as const }
      : { label: 'Disconnected', state: 'off' as const };

  return (
    <div className="app" id="agentscope-dashboard">
      {/* ── Header bar ─────────────────────────────────────────── */}
      <header className="app__header" id="dashboard-header">
        <div className="app__header-left">
          <h1 className="app__logo">
            <span className="app__logo-icon">◉</span> AgentScope
          </h1>

          {/* Run context — which run and which agents are on screen */}
          <div className="app__run-context">
            <span className="app__run-id" title={runContext.traceId ?? undefined}>
              {runContext.traceId ?? 'awaiting events…'}
            </span>
            {agentsLabel && <span className="app__run-agents">{agentsLabel}</span>}
          </div>

        </div>

        <div className="app__header-right">
          {/* Prominent anomaly-count badge (Flow 4 Step 3) */}
          <span
            className={`app__anomaly-badge ${stats.anomalies > 0 ? 'app__anomaly-badge--active' : ''}`}
            aria-label={`${stats.anomalies} anomalous ${stats.anomalies === 1 ? 'node' : 'nodes'}`}
            aria-live="polite"
          >
            <IconWarning size={13} />
            {stats.anomalies} {stats.anomalies === 1 ? 'Anomaly' : 'Anomalies'}
          </span>

          {/* Segmented LIVE / HISTORICAL toggle */}
          <div className="app__segmented" role="group" aria-label="View mode">
            <button
              type="button"
              className={`app__segment ${mode === 'live' ? 'app__segment--active' : ''}`}
              onClick={() => setMode('live')}
              aria-pressed={mode === 'live'}
            >
              Live
            </button>
            <button
              type="button"
              className={`app__segment ${mode === 'historical' ? 'app__segment--active' : ''}`}
              onClick={() => setMode('historical')}
              aria-pressed={mode === 'historical'}
            >
              Historical Replay
            </button>
          </div>

          {mode === 'historical' && (
            <select
              className="app__trace-select"
              value={historicalTraceId || ''}
              onChange={(e) => setHistoricalTraceId(e.target.value)}
              aria-label="Trace to replay"
            >
              {traceIds.length === 0 && <option value="">No traces recorded</option>}
              {traceIds.map((id) => (
                <option key={id} value={id}>Trace: {id}</option>
              ))}
            </select>
          )}

          {/* Read-only redaction indicator (Decision #4) */}
          <span
            className={`app__redaction ${isRedacted ? 'app__redaction--on' : ''}`}
            title={
              isRedacted
                ? 'SDK-side redaction is ON: inputs/outputs were scrubbed before leaving the agent process. The dashboard cannot toggle this.'
                : 'SDK-side redaction is OFF: full I/O capture. Redaction is configured in the SDK (Decision #4), not here.'
            }
          >
            {isRedacted ? <IconLock size={12} /> : <IconEye size={12} />}
            {isRedacted ? 'Redacted' : 'Full Capture'}
          </span>

          {/* Connection status */}
          <span className={`app__connection app__connection--${connection.state}`} aria-live="polite">
            <span className="app__connection-dot" aria-hidden="true" />
            {connection.label}
          </span>
        </div>
      </header>

      <main className="app__main">
        {/* ── Stats bar — the run at a glance (Flow 3/4, no clicking) ── */}
        <div className="app__statsbar">
        <div className="app__stat">
          <span className="app__stat-icon"><IconGraph size={14} /></span>
          <span className="app__stat-value">{stats.total}</span>
          <span className="app__stat-label">Nodes</span>
        </div>
        <div className="app__stat">
          <span className="app__stat-icon app__stat-icon--complete"><IconCheckCircle size={14} /></span>
          <span className="app__stat-value">{stats.complete}</span>
          <span className="app__stat-label">Complete</span>
        </div>
        <div className="app__stat">
          <span className="app__stat-icon app__stat-icon--active"><IconActivity size={14} /></span>
          <span className={`app__stat-value ${stats.active > 0 ? 'app__stat-value--active' : ''}`}>{stats.active}</span>
          <span className="app__stat-label">Active</span>
        </div>
        <div className={`app__stat ${stats.errors === 0 ? 'app__stat--muted' : ''}`}>
          <span className="app__stat-icon app__stat-icon--error"><IconXCircle size={14} /></span>
          <span className={`app__stat-value ${stats.errors > 0 ? 'app__stat-value--error' : ''}`}>{stats.errors}</span>
          <span className="app__stat-label">Errors</span>
        </div>
        <div className={`app__stat ${stats.anomalies === 0 ? 'app__stat--muted' : ''}`}>
          <span className="app__stat-icon app__stat-icon--anomalous"><IconWarning size={14} /></span>
          <span className={`app__stat-value ${stats.anomalies > 0 ? 'app__stat-value--anomalous' : ''}`}>{stats.anomalies}</span>
          <span className="app__stat-label">Anomalous</span>
        </div>
        </div>

        {/* ── Historical-load error banner ─────────────────────────── */}
        {mode === 'historical' && error && (
          <div role="alert" className="app__error-banner">
            Historical replay unavailable: {error}
          </div>
        )}

        {/* ── Graph canvas ───────────────────────────────────────── */}
        <div className="app__canvas" id="graph-canvas">
          <Legend />
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
              if (data.anomaly) return '#fb923c';
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
      </main>

      {/* ── Inspect panel (shown on node click) ────────────────── */}
      <InspectPanel span={selectedSpan} anomaly={selectedAnomaly} events={events} onClose={onPanelClose} />
    </div>
  );
}
