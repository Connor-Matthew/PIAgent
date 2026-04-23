export type NodeType = 'start' | 'llm' | 'rag' | 'tts' | 'end' | 'if_else' | 'iteration'
export type NodeVisualState = 'idle' | 'building' | 'running' | 'completed' | 'failed'

export type InputFieldType = 'text' | 'number' | 'select' | 'file'

export interface StartInputField {
  name: string
  type: InputFieldType
  required?: boolean
  default?: string | number
  options?: string[]
}

export type OutputSource = 'static' | 'reference'

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
  visualState?: NodeVisualState
  visualLabel?: string
  statusNote?: string
}

import type {
  WorkflowGraphV2,
  WorkflowNodeV2,
  WorkflowEdgeV2,
} from '../graph/contract'

export type WorkflowGraph = WorkflowGraphV2
export type WorkflowGraphNode = WorkflowNodeV2
export type WorkflowGraphEdge = WorkflowEdgeV2

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
  type:
    | 'workflow_start'
    | 'node_start'
    | 'node_stream'
    | 'node_heartbeat'
    | 'node_end'
    | 'branch_taken'
    | 'iteration_item_start'
    | 'iteration_item_end'
    | 'workflow_end'
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
  branch_id?: string
  condition_result?: boolean
  index?: number
  total?: number
  iteration_index?: number
  scope_id?: string
}
