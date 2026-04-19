/**
 * WorkflowGraph v2 contract — front-end side.
 *
 * This file mirrors `backend/core/graph_schema.py` in TypeScript.
 * It is the single source of truth for graph shape on the front end.
 */

export type NodeType =
  | 'start'
  | 'llm'
  | 'rag'
  | 'agent'
  | 'tts'
  | 'end'
  | 'if_else'
  | 'iteration'

export interface Position {
  x: number
  y: number
}

/**
 * v2 node shape.
 *
 * Structural fields (`parentId`, `branchId`) are top-level so that adapters
 * and the back end do not need to dig into `data`.
 */
export interface WorkflowNodeV2 {
  id: string
  type: NodeType
  position?: Position

  // Structural fields — used by compiler / engine
  parentId?: string
  branchId?: string

  // Display meta
  label?: string
  locked?: boolean

  // Business configuration (provider_id, prompt, etc.)
  config: Record<string, unknown>
}

/**
 * v2 edge shape.
 *
 * `sourceHandle` is UI metadata only and must not influence execution routing.
 */
export interface WorkflowEdgeV2 {
  id?: string
  source: string
  target: string
  sourceHandle?: string
}

/**
 * Canonical graph container.
 *
 * All new saves must write `version: 2`.  The adapter accepts v1 graphs
 * (missing `version`) and normalises them automatically.
 */
export interface WorkflowGraphV2 {
  version: 2
  nodes: WorkflowNodeV2[]
  edges: WorkflowEdgeV2[]
}

// ---------------------------------------------------------------------------
// v1 → v2 normalisation helpers
// ---------------------------------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/**
 * Upgrade a legacy v1 node to WorkflowNodeV2.
 *
 * In v1 `parentId` and `branchId` were hidden inside `data`.  We hoist them
 * to the top level and move everything else into `config`.
 */
export function upgradeV1Node(nodeDef: Record<string, unknown>): WorkflowNodeV2 {
  const data = isRecord(nodeDef.data) ? nodeDef.data : {}

  const config: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(data)) {
    if (key === 'parentId' || key === 'branchId' || key === 'label' || key === 'locked' || key === 'nodeType') {
      continue
    }
    config[key] = value
  }

  // If the v1 node stored config flat inside data.config, prefer that.
  if (isRecord(data.config)) {
    Object.assign(config, data.config)
  }

  return {
    id: String(nodeDef.id),
    type: String(nodeDef.type || data.nodeType || 'llm') as NodeType,
    position: isRecord(nodeDef.position)
      ? { x: Number(nodeDef.position.x), y: Number(nodeDef.position.y) }
      : undefined,
    parentId: typeof data.parentId === 'string' ? data.parentId : undefined,
    branchId: typeof data.branchId === 'string' ? data.branchId : undefined,
    label: typeof data.label === 'string' ? data.label : undefined,
    locked: typeof data.locked === 'boolean' ? data.locked : undefined,
    config,
  }
}

export function upgradeV1Edge(edgeDef: Record<string, unknown>): WorkflowEdgeV2 {
  return {
    id: typeof edgeDef.id === 'string' ? edgeDef.id : undefined,
    source: String(edgeDef.source),
    target: String(edgeDef.target),
    sourceHandle: typeof edgeDef.sourceHandle === 'string' ? edgeDef.sourceHandle : undefined,
  }
}

/**
 * Load a raw graph JSON (v1 or v2) and normalise to WorkflowGraphV2.
 */
export function loadGraph(raw: Record<string, unknown>): WorkflowGraphV2 {
  const version = raw.version

  if (version === 2) {
    const nodes = (Array.isArray(raw.nodes) ? raw.nodes : []).map((n) => {
      if (isRecord(n)) {
        // Already v2-ish — just ensure required fields
        const data = isRecord(n.data) ? n.data : {}
        const config = isRecord(data.config)
          ? data.config
          : isRecord(n.config)
            ? n.config
            : {}
        return {
          id: String(n.id),
          type: String(n.type || data.nodeType || 'llm') as NodeType,
          position: isRecord(n.position)
            ? { x: Number(n.position.x), y: Number(n.position.y) }
            : undefined,
          parentId: typeof n.parentId === 'string' ? n.parentId : typeof data.parentId === 'string' ? data.parentId : undefined,
          branchId: typeof n.branchId === 'string' ? n.branchId : typeof data.branchId === 'string' ? data.branchId : undefined,
          label: typeof n.label === 'string' ? n.label : typeof data.label === 'string' ? data.label : undefined,
          locked: typeof n.locked === 'boolean' ? n.locked : typeof data.locked === 'boolean' ? data.locked : undefined,
          config,
        } satisfies WorkflowNodeV2
      }
      return upgradeV1Node(n as Record<string, unknown>)
    })
    const edges = (Array.isArray(raw.edges) ? raw.edges : []).map((e) =>
      isRecord(e) ? upgradeV1Edge(e) : upgradeV1Edge({})
    )
    return { version: 2, nodes, edges }
  }

  // Treat everything else as v1 (legacy)
  const nodes = (Array.isArray(raw.nodes) ? raw.nodes : []).map((n) =>
    isRecord(n) ? upgradeV1Node(n) : upgradeV1Node({})
  )
  const edges = (Array.isArray(raw.edges) ? raw.edges : []).map((e) =>
    isRecord(e) ? upgradeV1Edge(e) : upgradeV1Edge({})
  )
  return { version: 2, nodes, edges }
}

/**
 * Serialise a WorkflowGraphV2 to the wire format.
 */
export function dumpGraph(graph: WorkflowGraphV2): Record<string, unknown> {
  return {
    version: 2,
    nodes: graph.nodes.map((n) => ({
      id: n.id,
      type: n.type,
      ...(n.position ? { position: n.position } : {}),
      ...(n.parentId ? { parentId: n.parentId } : {}),
      ...(n.branchId ? { branchId: n.branchId } : {}),
      ...(n.label ? { label: n.label } : {}),
      ...(n.locked !== undefined ? { locked: n.locked } : {}),
      config: n.config,
    })),
    edges: graph.edges.map((e) => ({
      ...(e.id ? { id: e.id } : {}),
      source: e.source,
      target: e.target,
      ...(e.sourceHandle ? { sourceHandle: e.sourceHandle } : {}),
    })),
  }
}
