export type NodeType = 'start' | 'llm' | 'rag' | 'agent' | 'tts' | 'end'

export type InputFieldType = 'text' | 'number' | 'select' | 'file'

export interface StartInputField {
  name: string
  type: InputFieldType
  required?: boolean
  default?: string | number
  options?: string[]
}

export type OutputSource = 'input' | 'reference'

export interface EndOutputField {
  name: string
  source: OutputSource
  value: string
}

export interface WorkflowNodeData {
  label: string
  nodeType: NodeType
  locked?: boolean
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
  nodeType?: string
  status: NodeStatus
  duration?: number
  output?: string
  chunks: string[]
  lastSeq?: number
  heartbeatMessage?: string
  heartbeatElapsed?: number
  progressLabel?: string
}

export interface StreamProgressDelta {
  current: number
  total: number
  message?: string
}

export interface SSEEvent {
  type: 'node_start' | 'node_stream' | 'node_heartbeat' | 'node_end' | 'workflow_end'
  node_id?: string
  node_type?: string
  status?: string
  delta?: string | StreamProgressDelta
  seq?: number
  elapsed?: number
  message?: string
  duration?: number
  output?: Record<string, unknown>
  answer?: string
  outputs?: Record<string, unknown>
  error?: string
}
