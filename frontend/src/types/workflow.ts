export type NodeType = 'start' | 'llm' | 'rag' | 'agent' | 'tts' | 'end'

export interface WorkflowNodeData {
  label: string
  nodeType: NodeType
  config: Record<string, unknown>
}

export interface WorkflowGraph {
  nodes: Array<{
    id: string
    type: string
    data: Record<string, unknown>
  }>
  edges: Array<{
    source: string
    target: string
  }>
}

export interface Workflow {
  id: string
  name: string
  description: string
  graph: WorkflowGraph
  created_at: string
}

export type NodeStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface NodeExecutionState {
  nodeId: string
  status: NodeStatus
  duration?: number
  output?: string
  chunks: string[]  // for streaming LLM output
}

export interface SSEEvent {
  type: 'node_start' | 'node_stream' | 'node_end' | 'workflow_end'
  node_id?: string
  node_type?: string
  status?: string
  chunk?: string
  duration?: number
  output?: Record<string, unknown>
}
