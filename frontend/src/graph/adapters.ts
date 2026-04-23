/**
 * Graph Adapter — bidirectional conversion between WorkflowGraphV2 and React Flow.
 *
 * Responsibilities:
 * - Load a WorkflowGraphV2 from the API into React Flow nodes/edges.
 * - Save React Flow state back to WorkflowGraphV2.
 * - Guarantee round-trip fidelity for structural fields:
 *   type, parentId, branchId, config, sourceHandle.
 */

import type { Node, Edge } from 'reactflow'
import type {
  WorkflowGraphV2,
  WorkflowNodeV2,
  WorkflowEdgeV2,
  NodeType,
} from './contract'

export interface ReactFlowNodeData {
  label: string
  nodeType: NodeType
  locked?: boolean
  config: Record<string, unknown>
  branchId?: string
  visualState?: 'idle' | 'building' | 'running' | 'completed' | 'failed'
  visualLabel?: string
  statusNote?: string
}

// ---------------------------------------------------------------------------
// v2 → React Flow
// ---------------------------------------------------------------------------

export function graphToReactFlow(
  graph: WorkflowGraphV2
): { nodes: Node<ReactFlowNodeData>[]; edges: Edge[] } {
  const idSet = new Set(graph.nodes.map((n) => n.id))
  const parentOf = new Map<string, string | undefined>(
    graph.nodes.map((n) => [n.id, n.parentId])
  )

  // Drop parentId references that are self-loops, unknown, or part of a cycle —
  // React Flow walks the parent chain recursively and will stack-overflow otherwise.
  const safeParent = (nodeId: string, parentId: string | undefined): string | undefined => {
    if (!parentId) return undefined
    if (parentId === nodeId) return undefined
    if (!idSet.has(parentId)) return undefined
    const seen = new Set<string>([nodeId])
    let cursor: string | undefined = parentId
    while (cursor) {
      if (seen.has(cursor)) return undefined
      seen.add(cursor)
      cursor = parentOf.get(cursor)
    }
    return parentId
  }

  const nodes: Node<ReactFlowNodeData>[] = graph.nodes.map((n) => {
    const parent = safeParent(n.id, n.parentId)
    return {
      id: n.id,
      type: n.type,
      position: n.position ?? { x: 0, y: 0 },
      ...(parent ? { parentNode: parent, extent: 'parent' as const } : {}),
      data: {
        label: n.label ?? n.type,
        nodeType: n.type,
        locked: n.locked,
        config: n.config,
        ...(n.branchId ? { branchId: n.branchId } : {}),
      },
    }
  })

  const edges: Edge[] = graph.edges.map((e) => ({
    id: e.id ?? `${e.source}-${e.target}`,
    source: e.source,
    target: e.target,
    ...(e.sourceHandle ? { sourceHandle: e.sourceHandle } : {}),
  }))

  return { nodes, edges }
}

// ---------------------------------------------------------------------------
// React Flow → v2
// ---------------------------------------------------------------------------

export function reactFlowToGraph(
  nodes: Node<ReactFlowNodeData>[],
  edges: Edge[]
): WorkflowGraphV2 {
  const graphNodes: WorkflowNodeV2[] = nodes.map((n) => {
    // Strip UI-only transient fields so they do not leak into persisted config
    const { visualState, visualLabel, statusNote, ...cleanConfig } = n.data.config
    return {
      id: n.id,
      type: n.data.nodeType,
      position: n.position,
      ...(n.parentNode ? { parentId: n.parentNode } : {}),
      ...(n.data.branchId ? { branchId: n.data.branchId } : {}),
      label: n.data.label,
      locked: n.data.locked,
      config: cleanConfig,
    }
  })

  const graphEdges: WorkflowEdgeV2[] = edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    ...(e.sourceHandle ? { sourceHandle: e.sourceHandle } : {}),
  }))

  return { version: 2, nodes: graphNodes, edges: graphEdges }
}
