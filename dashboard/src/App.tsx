import { useCallback, useEffect } from 'react';
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
  Edge,
  Node
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useWebSocket } from './hooks/useWebSocket';

export default function App() {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const { events, isConnected } = useWebSocket('ws://localhost:8000/ws');

  const onConnect = useCallback(
    (params: Connection | Edge) => setEdges((eds) => addEdge(params, eds)),
    [setEdges],
  );

  useEffect(() => {
    // Process incoming span events
    if (events.length === 0) return;
    
    const latestEvent = events[events.length - 1];
    
    setNodes((nds) => {
      const existingNode = nds.find((n) => n.id === latestEvent.span_id);
      
      // Determine node visual state
      const isComplete = latestEvent.end_time !== null;
      const isError = latestEvent.status.status === 'error';
      
      let borderColor = '#333'; // idle
      let borderWidth = 1;
      
      if (isError) {
        borderColor = 'red';
        borderWidth = 3;
      } else if (!isComplete) {
        borderColor = 'blue'; // active pulsing state
        borderWidth = 3;
      } else {
        borderColor = 'green'; // complete
        borderWidth = 2;
      }
      
      const style = {
        border: `${borderWidth}px solid ${borderColor}`,
        borderRadius: '5px',
        padding: '10px',
        backgroundColor: '#fff',
        transition: 'all 0.3s ease'
      };

      if (existingNode) {
        return nds.map((n) => 
          n.id === latestEvent.span_id 
            ? { ...n, style, data: { ...n.data, isComplete } } 
            : n
        );
      } else {
        // Just spread them out roughly for the placeholder
        const xOffset = nds.length * 150;
        return [
          ...nds,
          {
            id: latestEvent.span_id,
            position: { x: 50 + xOffset, y: 100 },
            data: { label: `${latestEvent.name}`, isComplete },
            style
          }
        ];
      }
    });

    setEdges((eds) => {
      if (latestEvent.parent_span_id) {
        const edgeId = `e-${latestEvent.parent_span_id}-${latestEvent.span_id}`;
        if (!eds.find(e => e.id === edgeId)) {
          return [
            ...eds,
            {
              id: edgeId,
              source: latestEvent.parent_span_id,
              target: latestEvent.span_id,
              animated: latestEvent.end_time === null // animated while active
            }
          ];
        } else {
            // Update edge animation if it completed
             return eds.map(e => e.id === edgeId ? { ...e, animated: latestEvent.end_time === null } : e);
        }
      }
      return eds;
    });

  }, [events, setNodes, setEdges]);

  return (
    <div style={{ width: '100vw', height: '100vh' }}>
      <div style={{ position: 'absolute', top: 10, left: 10, zIndex: 10, background: 'white', padding: 5, borderRadius: 5, border: '1px solid black' }}>
        Status: {isConnected ? 'Connected' : 'Disconnected'} | Events: {events.length}
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
      >
        <Controls />
        <MiniMap />
        <Background variant="dots" gap={12} size={1} />
      </ReactFlow>
    </div>
  );
}
