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

type WorkflowNodeInput = Node<WorkflowNodeData> | WorkflowGraphNode
type WorkflowEdgeInput =
  | Edge
  | (WorkflowGraphEdge & Partial<Pick<Edge, 'type' | 'animated' | 'label' | 'markerEnd'>>)

interface WorkflowState {
  nodes: Node<WorkflowNodeData>[]
  edges: Edge[]
  selectedNodeId: string | null
  workflowId: string | null
  workflowName: string
  isDraft: boolean

  onNodesChange: OnNodesChange
  onEdgesChange: OnEdgesChange
  onConnect: OnConnect
  addNode: (node: WorkflowNodeInput) => void
  addGraphEdge: (edge: WorkflowEdgeInput) => void
  startDraftBuild: (name: string) => void
  setSelectedNode: (id: string | null) => void
  updateNodeData: (id: string, data: Partial<WorkflowNodeData>) => void
  patchNodeConfig: (id: string, patch: Record<string, unknown>) => void
  setAllNodeVisuals: (patch: Pick<WorkflowNodeData, 'visualState' | 'visualLabel' | 'statusNote'> | Partial<Pick<WorkflowNodeData, 'visualState' | 'visualLabel' | 'statusNote'>>) => void
  setWorkflow: (id: string, name: string, nodes: WorkflowNodeInput[], edges: WorkflowEdgeInput[]) => void
  setDraftWorkflow: (name: string, nodes: WorkflowNodeInput[], edges: WorkflowEdgeInput[]) => void
  deleteEdge: (edgeId: string) => void
  toGraphJSON: () => WorkflowGraph
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
    value === 'agent' ||
    value === 'tts' ||
    value === 'end'
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
    Object.entries(rawData).filter(([key]) => !['label', 'nodeType', 'locked'].includes(key))
  )
}

function normalizeGraphNode(input: WorkflowNodeInput) {
  const rawData = isRecord(input.data) ? input.data : {}
  const nodeType = getNodeType(rawData.nodeType ?? input.type)
  const label = typeof rawData.label === 'string' ? rawData.label : nodeType
  const locked =
    isStartOrEnd(nodeType) || (typeof rawData.locked === 'boolean' ? rawData.locked : undefined)
  const config = getNodeConfig(rawData)

  return {
    id: input.id,
    type: input.type || nodeType,
    position: input.position || { x: 0, y: 0 },
    data: {
      label,
      nodeType,
      locked,
      config,
      ...pickUiData(rawData),
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
  isDraft: false,

  onNodesChange: (changes) => {
    const lockedIds = new Set(get().nodes.filter((n) => n.data.locked).map((n) => n.id))
    const allowedChanges = changes.filter((c) => {
      if (c.type === 'remove' && lockedIds.has(c.id)) return false
      return true
    })
    set({ nodes: applyNodeChanges(allowedChanges, get().nodes) })
  },

  onEdgesChange: (changes) =>
    set({ edges: applyEdgeChanges(changes, get().edges) }),

  onConnect: (connection) =>
    set({ edges: addEdgeToState(connection, get().edges) }),

  deleteEdge: (edgeId: string) =>
    set({ edges: get().edges.filter((e) => e.id !== edgeId) }),

  addNode: (node) =>
    set((state) => {
      const normalized = normalizeGraphNode(node)
      if (state.nodes.some((existing) => existing.id === normalized.id)) {
        return state
      }
      return { nodes: [...state.nodes, normalized] }
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

  startDraftBuild: (name) =>
    set({
      workflowId: null,
      workflowName: name,
      nodes: [],
      edges: [],
      isDraft: true,
      selectedNodeId: null,
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

  setAllNodeVisuals: (patch) =>
    set({
      nodes: get().nodes.map((n) => ({
        ...n,
        data: {
          ...n.data,
          ...patch,
        },
      })),
    }),

  setWorkflow: (id, name, graphNodes, edges) => {
    const nodes = normalizeGraphNodes(graphNodes)
    set({ workflowId: id, workflowName: name, nodes, edges: normalizeGraphEdges(edges), isDraft: false })
  },

  setDraftWorkflow: (name, graphNodes, edges) => {
    const nodes = normalizeGraphNodes(graphNodes)
    set({
      workflowId: null,
      workflowName: name,
      nodes,
      edges: normalizeGraphEdges(edges),
      isDraft: true,
      selectedNodeId: null,
    })
  },

  toGraphJSON: () => {
    const { nodes, edges } = get()
    return {
      nodes: nodes.map((n) => ({
        id: n.id,
        type: n.data.nodeType,
        position: n.position,
        data: {
          label: n.data.label,
          nodeType: n.data.nodeType,
          locked: n.data.locked,
          ...n.data.config,
        },
      })),
      edges: edges.map((e) => ({
        source: e.source,
        target: e.target,
      })),
    } as WorkflowGraph
  },
}))
