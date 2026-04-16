import { create } from 'zustand'
import {
  type Node,
  type Edge,
  type OnNodesChange,
  type OnEdgesChange,
  type OnConnect,
  applyNodeChanges,
  applyEdgeChanges,
  addEdge,
} from 'reactflow'
import type { WorkflowNodeData, WorkflowGraph } from '../types/workflow'

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
  addNode: (node: Node<WorkflowNodeData>) => void
  setSelectedNode: (id: string | null) => void
  updateNodeData: (id: string, data: Partial<WorkflowNodeData>) => void
  setWorkflow: (id: string, name: string, nodes: Node<WorkflowNodeData>[], edges: Edge[]) => void
  setDraftWorkflow: (name: string, nodes: Node<WorkflowNodeData>[], edges: Edge[]) => void
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

function normalizeGraphNodes(graphNodes: Node<WorkflowNodeData>[] | Array<any>) {
  const hasNodes = graphNodes && graphNodes.length > 0
  let nodes: Node<WorkflowNodeData>[] = hasNodes
    ? graphNodes.map((n) => {
        const rawData = (n as any).data || n.data || {}
        const nodeType = (rawData.nodeType as string) || n.type || 'llm'
        const label = (rawData.label as string) || nodeType
        const locked = isStartOrEnd(nodeType) ? true : (rawData.locked as boolean | undefined)
        let config: Record<string, unknown>
        if ('config' in rawData && typeof rawData.config === 'object' && rawData.config !== null) {
          config = rawData.config as Record<string, unknown>
        } else {
          const { label: _l, nodeType: _t, locked: _lk, id: _i, type: _ty, position: _p, ...rest } =
            rawData as Record<string, unknown>
          config = rest
        }
        return {
          id: n.id,
          type: n.type,
          position: (n as any).position || { x: 0, y: 0 },
          data: {
            label,
            nodeType: nodeType as any,
            locked,
            config,
          },
        }
      })
    : [defaultStartNode, defaultEndNode]

  const hasStart = nodes.some((n) => n.data.nodeType === 'start')
  const hasEnd = nodes.some((n) => n.data.nodeType === 'end')
  if (!hasStart) nodes.unshift({ ...defaultStartNode })
  if (!hasEnd) nodes.push({ ...defaultEndNode })

  return nodes
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
    set({ edges: addEdge(connection, get().edges) }),

  deleteEdge: (edgeId: string) =>
    set({ edges: get().edges.filter((e) => e.id !== edgeId) }),

  addNode: (node) =>
    set({ nodes: [...get().nodes, node] }),

  setSelectedNode: (id) =>
    set({ selectedNodeId: id }),

  updateNodeData: (id, data) =>
    set({
      nodes: get().nodes.map((n) =>
        n.id === id ? { ...n, data: { ...n.data, ...data } } : n
      ),
    }),

  setWorkflow: (id, name, graphNodes, edges) => {
    const nodes = normalizeGraphNodes(graphNodes)
    set({ workflowId: id, workflowName: name, nodes, edges: edges || [], isDraft: false })
  },

  setDraftWorkflow: (name, graphNodes, edges) => {
    const nodes = normalizeGraphNodes(graphNodes)
    set({
      workflowId: null,
      workflowName: name,
      nodes,
      edges: edges || [],
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
