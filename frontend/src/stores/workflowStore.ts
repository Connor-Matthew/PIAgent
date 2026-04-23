import { create } from 'zustand'
import {
  type Node,
  type Edge,
  type OnNodesChange,
  type OnEdgesChange,
  type OnConnect,
  applyNodeChanges,
  applyEdgeChanges,
  addEdge as addEdgeToState,
} from 'reactflow'
import type {
  NodeType,
  WorkflowNodeData,
  WorkflowGraph,
  WorkflowGraphEdge,
  WorkflowGraphNode,
} from '../types/workflow'
import { graphToReactFlow, reactFlowToGraph } from '../graph/adapters'
import { loadGraph } from '../graph/contract'

type WorkflowNodeInput = Node<WorkflowNodeData> | WorkflowGraphNode
type WorkflowEdgeInput =
  | Edge
  | (WorkflowGraphEdge & Partial<Pick<Edge, 'type' | 'animated' | 'label' | 'markerEnd'>>)

export interface WorkflowMeta {
  id: string
  name: string
}

export type SaveStatus = 'idle' | 'dirty' | 'saving' | 'saved' | 'error'

const OPEN_TABS_KEY = 'piagent:openTabs'

function loadOpenTabIds(): string[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(OPEN_TABS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed) && parsed.every((x) => typeof x === 'string')) {
      return parsed
    }
  } catch {
    // ignore
  }
  return []
}

function persistOpenTabIds(ids: string[]): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(OPEN_TABS_KEY, JSON.stringify(ids))
  } catch {
    // ignore
  }
}

interface WorkflowState {
  nodes: Node<WorkflowNodeData>[]
  edges: Edge[]
  selectedNodeId: string | null
  workflowId: string | null
  workflowName: string

  workflows: WorkflowMeta[]
  openTabIds: string[]
  saveStatus: SaveStatus

  onNodesChange: OnNodesChange
  onEdgesChange: OnEdgesChange
  onConnect: OnConnect
  addNode: (node: WorkflowNodeInput) => void
  addChildNode: (parentId: string, nodeType: NodeType, position: { x: number; y: number }) => void
  addGraphEdge: (edge: WorkflowEdgeInput) => void
  setSelectedNode: (id: string | null) => void
  updateNodeData: (id: string, data: Partial<WorkflowNodeData>) => void
  patchNodeConfig: (id: string, patch: Record<string, unknown>) => void
  setWorkflow: (id: string, name: string, nodes: WorkflowNodeInput[], edges: WorkflowEdgeInput[]) => void
  deleteEdge: (edgeId: string) => void
  deleteNode: (nodeId: string) => void
  toGraphJSON: () => WorkflowGraph

  setWorkflows: (workflows: WorkflowMeta[]) => void
  upsertWorkflowMeta: (meta: WorkflowMeta) => void
  removeWorkflowMeta: (id: string) => void
  openTab: (id: string) => void
  closeTab: (id: string) => string | null
  setSaveStatus: (status: SaveStatus) => void
}

export function createDefaultGraph(): WorkflowGraph {
  return {
    version: 2,
    nodes: [
      {
        id: 'start_1',
        type: 'start',
        position: { x: 80, y: 240 },
        label: '用户输入',
        locked: true,
        config: { inputs: [] },
      },
      {
        id: 'end_1',
        type: 'end',
        position: { x: 720, y: 240 },
        label: '结束',
        locked: true,
        config: { outputs: [], answer: '' },
      },
    ],
    edges: [],
  }
}

export const defaultStartNode: Node<WorkflowNodeData> = {
  id: 'start_1',
  type: 'start',
  position: { x: 80, y: 240 },
  data: {
    label: '用户输入',
    nodeType: 'start',
    locked: true,
    config: { inputs: [] },
  },
}

export const defaultEndNode: Node<WorkflowNodeData> = {
  id: 'end_1',
  type: 'end',
  position: { x: 720, y: 240 },
  data: {
    label: '结束',
    nodeType: 'end',
    locked: true,
    config: { outputs: [], answer: '' },
  },
}

function isStartOrEnd(type: string): boolean {
  return type === 'start' || type === 'end'
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isNodeType(value: unknown): value is NodeType {
  return (
    value === 'start' ||
    value === 'llm' ||
    value === 'rag' ||
    value === 'tts' ||
    value === 'end' ||
    value === 'if_else' ||
    value === 'iteration'
  )
}

function getNodeType(value: unknown): NodeType {
  return isNodeType(value) ? value : 'llm'
}

function pickUiData(rawData: Record<string, unknown>) {
  return {
    visualState: rawData.visualState as WorkflowNodeData['visualState'] | undefined,
    visualLabel: rawData.visualLabel as string | undefined,
    statusNote: rawData.statusNote as string | undefined,
  }
}

function getNodeConfig(rawData: Record<string, unknown>) {
  if (isRecord(rawData.config)) {
    return rawData.config
  }

  return Object.fromEntries(
    Object.entries(rawData).filter(
      ([key]) => !['label', 'nodeType', 'locked', 'parentId', 'branchId'].includes(key)
    )
  )
}

function normalizeGraphNode(input: WorkflowNodeInput) {
  // Detect v2 graph node (no .data property) vs React Flow node
  const isV2Node = !('data' in input)
  const rawData = isRecord((input as any).data) ? (input as any).data : {}

  const nodeType = getNodeType(isV2Node ? input.type : rawData.nodeType ?? input.type)
  const label = isV2Node
    ? (input as any).label ?? nodeType
    : typeof rawData.label === 'string'
      ? rawData.label
      : nodeType
  const locked = isV2Node
    ? (input as any).locked
    : isStartOrEnd(nodeType) || (typeof rawData.locked === 'boolean' ? rawData.locked : undefined)
  const config = isV2Node
    ? (isRecord((input as any).config) ? (input as any).config : {})
    : getNodeConfig(rawData)

  // Map backend parentId <=> React Flow parentNode + extent
  const parentNode =
    (input as any).parentNode ||
    (typeof (input as any).parentId === 'string' ? (input as any).parentId : undefined) ||
    (typeof rawData.parentId === 'string' ? rawData.parentId : undefined)
  const extent = parentNode ? ('parent' as const) : undefined

  return {
    id: input.id,
    type: input.type || nodeType,
    position: input.position || { x: 0, y: 0 },
    parentNode,
    extent,
    data: {
      label,
      nodeType,
      locked,
      config,
      ...(isV2Node ? {} : pickUiData(rawData)),
    },
  } satisfies Node<WorkflowNodeData>
}

function normalizeGraphEdge(input: WorkflowEdgeInput) {
  return {
    id: input.id || `${input.source}-${input.target}`,
    source: input.source,
    target: input.target,
    type: input.type,
    animated: input.animated,
    label: input.label,
    markerEnd: input.markerEnd,
    sourceHandle: (input as any).sourceHandle,
  } satisfies Edge
}

function normalizeGraphNodes(graphNodes: WorkflowNodeInput[]) {
  const hasNodes = graphNodes && graphNodes.length > 0
  const nodes: Node<WorkflowNodeData>[] = hasNodes
    ? graphNodes.map((n) => normalizeGraphNode(n))
    : [defaultStartNode, defaultEndNode]

  const hasStart = nodes.some((n) => n.data.nodeType === 'start')
  const hasEnd = nodes.some((n) => n.data.nodeType === 'end')
  if (!hasStart) nodes.unshift({ ...defaultStartNode })
  if (!hasEnd) nodes.push({ ...defaultEndNode })

  return nodes
}

function normalizeGraphEdges(graphEdges: WorkflowEdgeInput[] | undefined) {
  return (graphEdges || []).map((edge) => normalizeGraphEdge(edge))
}

export const useWorkflowStore = create<WorkflowState>((set, get) => ({
  nodes: [defaultStartNode, defaultEndNode],
  edges: [],
  selectedNodeId: null,
  workflowId: null,
  workflowName: 'Untitled Workflow',

  workflows: [],
  openTabIds: loadOpenTabIds(),
  saveStatus: 'idle',

  onNodesChange: (changes) => {
    const lockedIds = new Set(get().nodes.filter((n) => n.data.locked).map((n) => n.id))

    // Collect IDs being removed
    const removeIds = new Set(changes.filter((c) => c.type === 'remove').map((c) => c.id))

    // Cascade: also remove children whose parentNode is in removeIds
    const childIds = get().nodes
      .filter((n) => n.parentNode && removeIds.has(n.parentNode))
      .map((n) => n.id)
    childIds.forEach((id) => removeIds.add(id))

    const allowedChanges = changes.filter((c) => {
      if (c.type === 'remove' && lockedIds.has(c.id)) return false
      return true
    })

    // Append cascade removes for children (skip locked)
    const cascadeChanges = childIds
      .filter((id) => !lockedIds.has(id))
      .map((id) => ({ type: 'remove' as const, id }))

    const newNodes = applyNodeChanges([...allowedChanges, ...cascadeChanges], get().nodes)

    // Clean up edges connected to removed nodes
    const newEdges = get().edges.filter(
      (e) => !removeIds.has(e.source) && !removeIds.has(e.target)
    )

    set({ nodes: newNodes, edges: newEdges })
  },

  onEdgesChange: (changes) => {
    set({ edges: applyEdgeChanges(changes, get().edges) })
  },

  onConnect: (connection) => {
    set({ edges: addEdgeToState(connection, get().edges) })
  },

  deleteEdge: (edgeId: string) =>
    set({ edges: get().edges.filter((e) => e.id !== edgeId) }),

  deleteNode: (nodeId: string) => {
    const node = get().nodes.find((n) => n.id === nodeId)
    if (!node || node.data.locked) return
    get().onNodesChange([{ type: 'remove', id: nodeId }])
  },

  addNode: (node) =>
    set((state) => {
      const normalized = normalizeGraphNode(node)
      if (state.nodes.some((existing) => existing.id === normalized.id)) {
        return state
      }
      return { nodes: [...state.nodes, normalized] }
    }),

  addChildNode: (parentId, nodeType, position) =>
    set((state) => {
      const parent = state.nodes.find((n) => n.id === parentId)
      if (!parent) return state
      const id = `${nodeType}_${Date.now()}_${Math.floor(Math.random() * 1000)}`
      const child: Node<WorkflowNodeData> = {
        id,
        type: nodeType,
        position,
        parentNode: parentId,
        extent: 'parent',
        data: {
          label: nodeType,
          nodeType,
          locked: false,
          config: {},
        },
      }
      return { nodes: [...state.nodes, child] }
    }),

  addGraphEdge: (edge) =>
    set((state) => {
      const normalized = normalizeGraphEdge(edge)
      if (
        state.edges.some(
          (existing) =>
            existing.id === normalized.id ||
            (existing.source === normalized.source && existing.target === normalized.target)
        )
      ) {
        return state
      }
      return { edges: [...state.edges, normalized] }
    }),

  setSelectedNode: (id) =>
    set({ selectedNodeId: id }),

  updateNodeData: (id, data) =>
    set({
      nodes: get().nodes.map((n) =>
        n.id === id ? { ...n, data: { ...n.data, ...data } } : n
      ),
    }),

  patchNodeConfig: (id, patch) =>
    set({
      nodes: get().nodes.map((n) =>
        n.id === id
          ? {
              ...n,
              data: {
                ...n.data,
                config: {
                  ...(n.data.config || {}),
                  ...patch,
                },
              },
            }
          : n
      ),
    }),

  setWorkflow: (id, name, graphNodes, edges) => {
    const graph = loadGraph({ version: 2, nodes: graphNodes, edges })
    const converted = graphToReactFlow(graph)
    set({
      workflowId: id,
      workflowName: name,
      nodes: normalizeGraphNodes(converted.nodes),
      edges: normalizeGraphEdges(converted.edges),
      selectedNodeId:
        get().selectedNodeId && converted.nodes.some((n) => n.id === get().selectedNodeId)
          ? get().selectedNodeId
          : null,
    })
  },

  toGraphJSON: () => {
    const { nodes, edges } = get()
    return reactFlowToGraph(nodes, edges)
  },

  setWorkflows: (workflows) => {
    const validIds = new Set(workflows.map((w) => w.id))
    const openTabIds = get().openTabIds.filter((id) => validIds.has(id))
    persistOpenTabIds(openTabIds)
    set({ workflows, openTabIds })
  },

  upsertWorkflowMeta: (meta) =>
    set((state) => {
      const idx = state.workflows.findIndex((w) => w.id === meta.id)
      if (idx === -1) {
        return { workflows: [...state.workflows, meta] }
      }
      const next = state.workflows.slice()
      next[idx] = meta
      return { workflows: next }
    }),

  removeWorkflowMeta: (id) =>
    set((state) => {
      const workflows = state.workflows.filter((w) => w.id !== id)
      const openTabIds = state.openTabIds.filter((tid) => tid !== id)
      persistOpenTabIds(openTabIds)
      return { workflows, openTabIds }
    }),

  openTab: (id) =>
    set((state) => {
      if (state.openTabIds.includes(id)) return state
      const openTabIds = [...state.openTabIds, id]
      persistOpenTabIds(openTabIds)
      return { openTabIds }
    }),

  closeTab: (id) => {
    const { openTabIds, workflowId } = get()
    if (!openTabIds.includes(id)) return workflowId
    const nextTabs = openTabIds.filter((tid) => tid !== id)
    persistOpenTabIds(nextTabs)

    let fallback: string | null = workflowId
    if (workflowId === id) {
      const idx = openTabIds.indexOf(id)
      fallback = nextTabs[idx] ?? nextTabs[idx - 1] ?? nextTabs[nextTabs.length - 1] ?? null
    }

    set({ openTabIds: nextTabs })
    return fallback
  },

  setSaveStatus: (status) => set({ saveStatus: status }),
}))
