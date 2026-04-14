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

  onNodesChange: OnNodesChange
  onEdgesChange: OnEdgesChange
  onConnect: OnConnect
  addNode: (node: Node<WorkflowNodeData>) => void
  setSelectedNode: (id: string | null) => void
  updateNodeData: (id: string, data: Partial<WorkflowNodeData>) => void
  setWorkflow: (id: string, name: string, nodes: Node<WorkflowNodeData>[], edges: Edge[]) => void
  toGraphJSON: () => WorkflowGraph
}

export const useWorkflowStore = create<WorkflowState>((set, get) => ({
  nodes: [],
  edges: [],
  selectedNodeId: null,
  workflowId: null,
  workflowName: 'Untitled Workflow',

  onNodesChange: (changes) =>
    set({ nodes: applyNodeChanges(changes, get().nodes) }),

  onEdgesChange: (changes) =>
    set({ edges: applyEdgeChanges(changes, get().edges) }),

  onConnect: (connection) =>
    set({ edges: addEdge(connection, get().edges) }),

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

  setWorkflow: (id, name, nodes, edges) =>
    set({ workflowId: id, workflowName: name, nodes, edges }),

  toGraphJSON: () => {
    const { nodes, edges } = get()
    return {
      nodes: nodes.map((n) => ({
        id: n.id,
        type: n.data.nodeType,
        data: n.data.config,
      })),
      edges: edges.map((e) => ({
        source: e.source,
        target: e.target,
      })),
    }
  },
}))
