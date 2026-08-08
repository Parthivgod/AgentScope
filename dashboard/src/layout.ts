/**
 * layout.ts — Dagre auto-layout for the AgentScope execution graph.
 *
 * Uses @dagrejs/dagre to compute hierarchical (top-to-bottom) positions
 * for React Flow nodes/edges. This is the single layout function used by
 * both live and historical rendering paths (RULES.md §3 invariant #5).
 *
 * References:
 *   - Build Plan §1 Decision 1: hierarchical/dagre layout
 *   - PRD §6.2: dagre chosen over force-directed for clear flow direction
 *   - Flow 3 Step 3: dagre layout recomputed as new nodes/edges arrive
 */

import dagre from '@dagrejs/dagre';
import type { Node, Edge } from '@xyflow/react';

/** Default dimensions used for dagre node sizing */
const NODE_WIDTH = 220;
const NODE_HEIGHT = 72;

export interface LayoutOptions {
  /** Layout direction: TB = top-to-bottom, LR = left-to-right */
  direction?: 'TB' | 'LR';
  /** Horizontal spacing between nodes */
  nodesep?: number;
  /** Vertical spacing between ranks (layers) */
  ranksep?: number;
}

/**
 * Compute hierarchical positions for all nodes using dagre.
 *
 * Accepts the current React Flow nodes and edges, returns a new
 * nodes array with updated `position` values. Edges are returned
 * unchanged (React Flow handles edge routing from node positions).
 *
 * This function is pure — it does not mutate the input arrays.
 */
export function getLayoutedElements(
  nodes: Node[],
  edges: Edge[],
  options: LayoutOptions = {}
): { nodes: Node[]; edges: Edge[] } {
  const {
    direction = 'TB',
    nodesep = 60,
    ranksep = 80,
  } = options;

  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({
    rankdir: direction,
    nodesep,
    ranksep,
    marginx: 20,
    marginy: 20,
  });

  // Register nodes with dagre
  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, {
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
    });
  });

  // Register edges with dagre
  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  // Run the layout algorithm
  dagre.layout(dagreGraph);

  // Map dagre-computed positions back onto React Flow nodes.
  // Dagre gives center coordinates; React Flow uses top-left,
  // so we offset by half the node dimensions.
  const layoutedNodes = nodes.map((node) => {
    const dagreNode = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: dagreNode.x - NODE_WIDTH / 2,
        y: dagreNode.y - NODE_HEIGHT / 2,
      },
    };
  });

  return { nodes: layoutedNodes, edges };
}

export { NODE_WIDTH, NODE_HEIGHT };
