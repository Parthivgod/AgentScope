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

import { useWebSocket, type SpanEvent } from './hooks/useWebSocket';
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
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const { events, isConnected } = useWebSocket('ws://localhost:8000/ws');

  // Track the raw span data keyed by span_id for InspectPanel lookups
  const [spanMap, setSpanMap] = useState<Map<string, SpanEvent>>(new Map());

  // Currently selected span for inspection
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const selectedSpan = selectedSpanId ? spanMap.get(selectedSpanId) ?? null : null;

  // ── Process incoming events → build nodes/edges ───────────────────
  useEffect(() => {
    if (events.length === 0) return;

    const latestEvent = events[events.length - 1];

    // Update the span map with latest data
    setSpanMap((prev) => {
      const next = new Map(prev);
      next.set(latestEvent.span_id, latestEvent);
      return next;
    });

    // Build/update nodes
    setNodes((nds) => {
      const status = spanStatus(latestEvent);
      const duration = computeDuration(latestEvent.start_time, latestEvent.end_time);

      const nodeData: AgentNodeData = {
        label: latestEvent.name,
        spanType: latestEvent.span_type,
        status,
        agentId: latestEvent.agent_id,
        tokenUsage: latestEvent.token_usage,
        duration,
      };

      const existingIdx = nds.findIndex((n) => n.id === latestEvent.span_id);

      if (existingIdx >= 0) {
        // Update existing node
        const updated = [...nds];
        updated[existingIdx] = {
          ...updated[existingIdx],
          data: nodeData,
        };
        return updated;
      }

      // Add new node (position will be overridden by dagre)
      return [
        ...nds,
        {
          id: latestEvent.span_id,
          type: 'agentNode',
          position: { x: 0, y: 0 },
          data: nodeData,
        },
      ];
    });

    // Build/update edges
    setEdges((eds) => {
      if (!latestEvent.parent_span_id) return eds;

      const edgeId = `e-${latestEvent.parent_span_id}-${latestEvent.span_id}`;
      const existingIdx = eds.findIndex((e) => e.id === edgeId);

      if (existingIdx >= 0) {
        // Update animation state
        const updated = [...eds];
        updated[existingIdx] = {
          ...updated[existingIdx],
          animated: latestEvent.end_time === null,
        };
        return updated;
      }

      return [
        ...eds,
        {
          id: edgeId,
          source: latestEvent.parent_span_id,
          target: latestEvent.span_id,
          animated: latestEvent.end_time === null,
          style: { stroke: '#475569', strokeWidth: 1.5 },
        },
      ];
    });
  }, [events, setNodes, setEdges]);

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
    nodes.forEach((n) => {
      const data = n.data as AgentNodeData;
      if (data.status === 'active') active++;
      if (data.status === 'error') errors++;
    });
    return { total: nodes.length, active, errors };
  }, [nodes]);

  return (
    <div className="app" id="agentscope-dashboard">
      {/* ── Header bar ─────────────────────────────────────────── */}
      <header className="app__header" id="dashboard-header">
        <div className="app__header-left">
          <h1 className="app__logo">
            <span className="app__logo-icon">◉</span> AgentScope
          </h1>
          <span className={`app__connection ${isConnected ? 'app__connection--on' : ''}`}>
            {isConnected ? 'Live' : 'Disconnected'}
          </span>
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
          <div className="app__stat">
            <span className="app__stat-value">{events.length}</span>
            <span className="app__stat-label">Events</span>
          </div>
        </div>
      </header>

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
      <InspectPanel span={selectedSpan} onClose={onPanelClose} />
    </div>
  );
}
